import sys
import time
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from app.classify import (  # noqa: E402
    LABELS,
    _brightness,
    _classify_with_brightness,
    _classify_with_vlm,
)

DATA_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "eval_data"
DELAY = 2.0  # seconds between calls, to stay under free-tier rate limits
EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def load_samples():
    known = set(LABELS)
    for d in sorted(p for p in DATA_DIR.iterdir() if p.is_dir()):
        if d.name not in known:
            print(f"WARNING: folder '{d.name}' doesn't match any label, skipping")
    for label in LABELS:
        folder = DATA_DIR / label
        if not folder.is_dir():
            print(f"WARNING: missing folder for '{label}'")
            continue
        files = [p for p in sorted(folder.iterdir()) if p.suffix.lower() in EXTS]
        skipped = [p.name for p in folder.iterdir() if p.is_file() and p.suffix.lower() not in EXTS]
        print(f"{label}: {len(files)} images" + (f" (skipped unsupported: {skipped[:3]})" if skipped else ""))
        for path in files:
            yield path, label


def report(name, y_true, y_pred):
    correct = sum(t == p for t, p in zip(y_true, y_pred))
    print(f"\n=== {name}: accuracy {correct}/{len(y_true)} = {correct / len(y_true):.1%} ===")

    print(f"{'label':<20}{'precision':>10}{'recall':>10}{'support':>9}")
    for label in LABELS:
        tp = sum(t == label and p == label for t, p in zip(y_true, y_pred))
        pred_n = sum(p == label for p in y_pred)
        true_n = sum(t == label for t in y_true)
        prec = tp / pred_n if pred_n else 0.0
        rec = tp / true_n if true_n else 0.0
        print(f"{label:<20}{prec:>10.2f}{rec:>10.2f}{true_n:>9}")

    cols = list(LABELS) + ["error"]
    print("\nConfusion matrix (rows = true, cols = predicted)")
    print(f"{'':<20}" + "".join(f"{c[:9]:>10}" for c in cols))
    counts = Counter(zip(y_true, y_pred))
    for t in LABELS:
        print(f"{t:<20}" + "".join(f"{counts[(t, p)]:>10}" for p in cols))


def main():
    y_true, y_vlm, y_base, errors = [], [], [], 0
    for path, true_label in load_samples():
        try:
            image = Image.open(path).convert("RGB")
        except Exception as exc:
            print(f"SKIP {path.name}: unreadable image ({exc})")
            continue
        brightness = _brightness(image)
        y_base.append(_classify_with_brightness(brightness)["label"])
        try:
            pred = _classify_with_vlm(image, brightness)["label"]
        except Exception as exc:
            errors += 1
            print(f"ERROR {path.name}: {exc}")
            pred = "error"
        y_true.append(true_label)
        y_vlm.append(pred)
        print(f"{path.parent.name}/{path.name}: true={true_label} pred={pred}")
        time.sleep(DELAY)

    if not y_true:
        sys.exit(f"No images found in {DATA_DIR}")
    print(f"\nModel errors: {errors}/{len(y_true)}")
    report("VLM", y_true, y_vlm)
    report("Brightness baseline", y_true, y_base)


if __name__ == "__main__":
    main()
