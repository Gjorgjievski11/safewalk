from functools import lru_cache
from io import BytesIO
import os
from typing import Any

from PIL import Image, ImageStat


LABELS = ("parked_on_sidewalk", "overgrown", "dark_street", "broken_light", "none")


def _brightness(image: Image.Image) -> float:
    return round(sum(ImageStat.Stat(image.convert("L")).mean), 2)


@lru_cache(maxsize=1)
def _clip_model() -> tuple[Any, Any, Any] | None:
    if os.getenv("SAFEWALK_ENABLE_CLIP") != "1":
        return None
    try:
        import open_clip
        import torch

        model, _, preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="laion2b_s34b_b79k"
        )
        tokenizer = open_clip.get_tokenizer("ViT-B-32")
        model.eval()
        return model, preprocess, tokenizer
    except (ImportError, OSError, RuntimeError):
        return None


def classify_image(content: bytes) -> dict[str, float | str]:
    try:
        image = Image.open(BytesIO(content)).convert("RGB")
    except Exception as exc:
        raise ValueError("uploaded file is not a valid image") from exc

    brightness = _brightness(image)
    clip = _clip_model()
    if clip is not None:
        model, preprocess, tokenizer = clip
        import torch

        prompts = [f"a photo of {label.replace('_', ' ')}" for label in LABELS]
        with torch.no_grad():
            logits = model(
                preprocess(image).unsqueeze(0),
                tokenizer(prompts),
            )
            probabilities = logits.softmax(dim=-1)[0]
        index = int(probabilities.argmax())
        return {
            "label": LABELS[index],
            "confidence": round(float(probabilities[index]), 4),
            "brightness": brightness,
        }

    # Keep the API useful before the optional model weights are downloaded.
    if brightness < 64:
        label, confidence = "dark_street", 0.75
    else:
        label, confidence = "none", 0.5
    return {"label": label, "confidence": confidence, "brightness": brightness}