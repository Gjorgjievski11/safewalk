"""Collect test images per label from Wikimedia Commons + Openverse (CC-licensed).

Usage (from repo root):
    uv add requests
    uv run python scripts/scrape_images.py            # ~25 per label
    uv run python scripts/scrape_images.py --per-label 40

Output:
    data/scraped/<label>/<hash>.jpg
    data/scraped/attribution.csv   (title, author, license, source url)

These are noisy. Skim each folder and delete wrong ones before measuring accuracy.
"""
import argparse
import csv
import hashlib
import io
import time
from pathlib import Path

import requests
from PIL import Image

OUT = Path("data/scraped")
HEADERS = {"User-Agent": "safewalk-hackathon/0.1 (student project; contact via github)"}

QUERIES = {
    "parked_on_sidewalk": [
        "car parked on sidewalk",
        "cars blocking sidewalk",
        "illegal parking pavement pedestrians",
    ],
    "overgrown": [
        "overgrown sidewalk",
        "vegetation covering footpath",
        "weeds overgrown path city",
    ],
    "dark_street": [
        "dark street at night",
        "unlit street night",
        "poorly lit alley night",
    ],
    "broken_light": [
        "broken street lamp",
        "damaged street light",
        "street lamp out of order",
    ],
    "none": [
        "empty sidewalk",
        "clean pedestrian sidewalk",
        "city sidewalk daytime",
    ],
}


def commons(query, limit):
    r = requests.get(
        "https://commons.wikimedia.org/w/api.php",
        params={
            "action": "query", "format": "json", "generator": "search",
            "gsrsearch": f"{query} filetype:bitmap", "gsrnamespace": 6,
            "gsrlimit": limit, "prop": "imageinfo",
            "iiprop": "url|extmetadata", "iiurlwidth": 640,
        },
        headers=HEADERS, timeout=20,
    )
    r.raise_for_status()
    for page in r.json().get("query", {}).get("pages", {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        yield {
            "url": info.get("thumburl") or info.get("url"),
            "title": page.get("title", ""),
            "author": meta.get("Artist", {}).get("value", "")[:120],
            "license": meta.get("LicenseShortName", {}).get("value", ""),
            "source": info.get("descriptionurl", ""),
        }


def openverse(query, limit):
    r = requests.get(
        "https://api.openverse.org/v1/images/",
        params={"q": query, "page_size": min(limit, 20), "mature": "false"},
        headers=HEADERS, timeout=20,
    )
    r.raise_for_status()
    for it in r.json().get("results", []):
        yield {
            "url": it.get("thumbnail") or it.get("url"),
            "title": it.get("title", ""),
            "author": it.get("creator") or "",
            "license": f"{it.get('license', '')} {it.get('license_version', '')}".strip(),
            "source": it.get("foreign_landing_url", ""),
        }


def save(item, folder):
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
        if min(img.size) < 200:
            return None
        img.thumbnail((800, 800))
        img.save(path, "JPEG", quality=88)
        return path
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-label", type=int, default=25)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    attr_file = OUT / "attribution.csv"
    new_file = not attr_file.exists()
    with attr_file.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["file", "label", "title", "author", "license", "source"])
        for label, queries in QUERIES.items():
            folder = OUT / label
            folder.mkdir(exist_ok=True)
            got = len(list(folder.glob("*.jpg")))
            for q in queries:
                for fetch in (commons, openverse):
                    if got >= args.per_label:
                        break
                    try:
                        items = list(fetch(q, 20))
                    except Exception as e:
                        print(f"  ! {fetch.__name__} '{q}': {e}")
                        continue
                    for it in items:
                        if got >= args.per_label:
                            break
                        p = save(it, folder)
                        if p:
                            got += 1
                            w.writerow([p.name, label, it["title"], it["author"],
                                        it["license"], it["source"]])
                    time.sleep(1)  # be polite
            print(f"{label}: {got} images")


if __name__ == "__main__":
    main()