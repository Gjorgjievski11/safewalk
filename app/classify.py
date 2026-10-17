import base64
import json
import logging
import os
import re
from functools import lru_cache
from io import BytesIO

from openai import OpenAI
from PIL import Image, ImageStat

logger = logging.getLogger(__name__)

LABELS = ("invalid_parked_cars", "overgrown", "dark_streets", "broken-streetlights", "none")

BASE_URL = os.getenv("VLM_BASE_URL", "https://api.groq.com/openai/v1")
DEFAULT_MODEL = "qwen/qwen3.8-27b"

PROMPT = (
    "You are classifying a photo of a street or sidewalk for a pedestrian-safety app. "
    f"Pick exactly one label from {list(LABELS)}:\n"
    "- parked_on_sidewalk: vehicles blocking the sidewalk\n"
    "- overgrown: vegetation blocking or covering the path\n"
    "- dark_street: poorly lit street or sidewalk\n"
    "- broken_light: a visibly broken or non-working street light\n"
    "- none: no issue visible\n"
    'Reply only with JSON: {"label": "<label>", "confidence": <float between 0 and 1>}.'
)


def _brightness(image: Image.Image) -> float:
    return round(sum(ImageStat.Stat(image.convert("L")).mean), 2)


@lru_cache(maxsize=1)
def _client() -> OpenAI | None:
    api_key = os.getenv("VLM_API_KEY")
    if not api_key:
        return None
    return OpenAI(base_url=BASE_URL, api_key=api_key, timeout=30.0, max_retries=5)


def _parse_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON in model reply: {text[:200]!r}")
    return json.loads(match.group(0))


def _classify_with_vlm(image: Image.Image, brightness: float) -> dict[str, float | str]:
    client = _client()
    if client is None:
        raise RuntimeError("VLM_API_KEY is not set")

    # Re-encode as JPEG so the mime type always matches and large uploads shrink.
    thumb = image.copy()
    thumb.thumbnail((1024, 1024))
    buf = BytesIO()
    thumb.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()

    resp = client.chat.completions.create(
        model=os.getenv("VLM_MODEL", DEFAULT_MODEL),
        temperature=0,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                ],
            }
        ],
    )

    result = _parse_json(resp.choices[0].message.content or "")
    label = result.get("label")
    if label not in LABELS:
        label, confidence = "none", 0.0
    else:
        try:
            confidence = max(0.0, min(1.0, float(result.get("confidence", 0.0))))
        except (TypeError, ValueError):
            confidence = 0.0

    return {"label": label, "confidence": round(confidence, 4), "brightness": brightness}


def _classify_with_brightness(brightness: float) -> dict[str, float | str]:
    # Fallback when the model is unavailable (no key, rate limit, network error).
    if brightness < 64:
        label, confidence = "dark_street", 0.75
    else:
        label, confidence = "none", 0.5
    return {"label": label, "confidence": confidence, "brightness": brightness}


def classify_image(content: bytes) -> dict[str, float | str]:
    try:
        image = Image.open(BytesIO(content)).convert("RGB")
    except Exception as exc:
        raise ValueError("uploaded file is not a valid image") from exc

    brightness = _brightness(image)

    try:
        return _classify_with_vlm(image, brightness)
    except Exception:
        logger.exception("VLM classification failed, using brightness fallback")
        return _classify_with_brightness(brightness)
