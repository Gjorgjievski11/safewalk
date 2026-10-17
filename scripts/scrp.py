"""Collect test images per label from Wikimedia Commons + Openverse (CC-licensed).

Usage (from repo root):
    uv add requests
    uv run python scripts/scrape_images.py                # ~25 per label
    uv run python scripts/scrape_images.py --per-label 40
    uv run python scripts/scrape_images.py --labels broken_light overgrown

Output:
    data/scraped/<label>/<hash>.jpg
    data/scraped/attribution.csv   (file, label, title, author, license, source)

Results are still noisy. Skim each folder and delete wrong ones by eye
before measuring accuracy.
"""
import argparse
import csv
import hashlib
import io
import re
import time
from pathlib import Path

import requests
from PIL import Image

OUT = Path("data/scraped")
HEADERS = {"User-Agent": "safewalk-hackathon/0.1 (student project; contact via github)"}

QUERIES = {
    "parked_on_sidewalk": [
        '"parked on the sidewalk"',
        '"parked on the pavement"',
        '"sidewalk parking" car',
        '"illegal parking" sidewalk -map -sign',
        "cars parked sidewalk Skopje",
        "cars parked sidewalk Belgrade",
    ],
    "overgrown": [
        '"overgrown" footpath -garden',
        '"overgrown" pavement weeds',
        '"weeds" growing sidewalk',
        "bushes blocking sidewalk",
        '"overgrown" sidewalk -forest',
    ],
    "dark_street": [
        '"street at night" empty',
        '"empty street" night lamp',
        '"alley" night dark',
        '"dimly lit" street',
        "Skopje street night",
        '"dark street"',
    ],
    "broken_light": [
        '"broken street light"',
        '"broken streetlight"',
        '"broken street lamp"',
        '"streetlight" vandalized',
        '"lamp post" damaged -accident',
    ],
    "none": [
        "empty sidewalk daytime",
        "residential street sidewalk -snow",
        '"pavement" pedestrians street',
        "Skopje street sidewalk",
        '"footpath" city street',
    ],
}

# A result is kept only if its title contains at least one of these (lowercase).
REQUIRE = {
    "parked_on_sidewalk": ["park", "sidewalk", "pavement", "car"],
    "overgrown": ["overgrown", "weed", "bush", "vegetation", "grass", "path"],
    "dark_street": ["night", "dark", "alley", "lit", "street"],
    "broken_light": ["lamp", "light", "lantern", "pole"],
    "none": ["sidewalk", "pavement", "footpath", "street", "pedestrian"],
}

# Titles containing any of these are always dropped.
BLOCK = [
    "map", "logo", "icon", "diagram", "poster", "painting", "drawing",
    "illustration", "cartoon", "screenshot", "flag", "coat of arms",
    "stamp", "postcard", "sketch", "render", "model", "toy",
]

MIN_SIDE = 300
MAX_SIDE = 800


def strip_html(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()


def commons(query, limit=30):
    r = requests.get(
        "https://commons.wikimedia.org/w/api.php",
        params={
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f"{query} filetype:bitmap",
            "gsrnamespace": 6,
            "gsrlimit": limit,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "iiurlwidth": 800,
        },
        headers=HEADERS,
        timeout=20,
    )
    r.raise_for_status()
    for page in r.json().get("query", {}).get("pages", {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        title = page.get("title", "").replace("File:", "")
        yield {
            "url": info.get("thumburl") or info.get("url"),
            "title": title,
            "author": strip_html(meta.get("Artist", {}).get("value", ""))[:120],
            "license": meta.get("LicenseShortName", {}).get("value", ""),
            "source": info.get("descriptionurl", ""),
        }


def openverse(query, limit=20):
    # Openverse supports quotes and "-" less reliably; strip the minus terms.
    q = " ".join(t for t in query.split() if not t.startswith("-"))
    r = requests.get(
        "https://api.openverse.org/v1/images/",
        params={
            "q": q,
            "page_size": min(limit, 20),
            "mature": "false",
            "category": "photograph",
        },
        headers=HEADERS,
        timeout=20,
    )
    r.raise_for_status()
    for it in r.json().get("results", []):
        yield {
            "url": it.get("thumbnail") or it.get("url"),
            "title": it.get("title") or "",
            "author": it.get("creator") or "",
            "license": f"{it.get('license', '')} {it.get('license_version', '')}".strip(),
            "source": it.get("foreign_landing_url", ""),
        }


def title_ok(label, title):
    t = title.lower()
    if any(b in t for b in BLOCK):
        return False
    return any(k in t for k in REQUIRE[label])


def save(item, folder, seen_hashes):
    if not item["url"]:
        return None
    h = hashlib.sha1(item["url"].encode()).hexdigest()[:12]
    path = folder / f"{h}.jpg"
    if path.exists():
        return None
    try:
        resp = requests.get(item["url"], headers=HEADERS, timeout=20)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        if min(img.size) < MIN_SIDE:
            return None
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        # cheap near-duplicate check on a tiny grayscale version
        tiny = img.resize((8, 8)).convert("L")
        avg = sum(tiny.getdata()) / 64
        sig = "".join("1" if p > avg else "0" for p in tiny.getdata())
        if sig in seen_hashes:
            return None
        seen_hashes.add(sig)
        img.save(path, "JPEG", quality=88)
        return path
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-label", type=int, default=25)
    ap.add_argument("--labels", nargs="+", choices=list(QUERIES), default=list(QUERIES))
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    attr_file = OUT / "attribution.csv"
    new_file = not attr_file.exists()
    seen = set()

    with attr_file.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["file", "label", "title", "author", "license", "source"])

        for label in args.labels:
            folder = OUT / label
            folder.mkdir(exist_ok=True)
            got = len(list(folder.glob("*.jpg")))
            print(f"\n[{label}] already have {got}")

            for q in QUERIES[label]:
                for fetch in (commons, openverse):
                    if got >= args.per_label:
                        break
                    try:
                        items = list(fetch(q))
                    except Exception as e:
                        print(f"  ! {fetch.__name__} {q!r}: {e}")
                        continue

                    kept = 0
                    for it in items:
                        if got >= args.per_label:
                            break
                        if not title_ok(label, it["title"]):
                            continue
                        p = save(it, folder, seen)
                        if p:
                            got += 1
                            kept += 1
                            w.writerow([p.name, label, it["title"], it["author"],
                                        it["license"], it["source"]])
                    print(f"  {fetch.__name__:9} {q!r}: {kept} kept ({len(items)} found)")
                    time.sleep(1)  # be polite

            print(f"[{label}] total {got}")

    print("\nDone. Open data/scraped/ and delete the wrong ones by hand.")


if __name__ == "__main__":
    main()