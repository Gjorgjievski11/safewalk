import os


def draft_report(label: str, latitude: float, longitude: float, brightness: float | None = None) -> str:
    descriptions = {
        "parked_on_sidewalk": "A vehicle is blocking the sidewalk.",
        "overgrown": "Overgrown vegetation is blocking or narrowing the walking path.",
        "dark_street": "This street or walking path is too dark.",
        "broken_light": "A street light appears to be broken.",
        "none": "A walking-accessibility issue was reported.",
    }
    base = descriptions.get(label, descriptions["none"])
    return f"{base} Location: {latitude:.5f}, {longitude:.5f}."