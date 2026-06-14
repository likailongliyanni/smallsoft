from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


def save_privacy_focus_screenshot(
    raw_bytes: bytes,
    out_path: Path,
    focus_x: float,
    focus_y: float,
    radius: int = 160,
    blur_radius: int = 18,
    quality: int = 82,
) -> dict:
    image = Image.open(BytesIO(raw_bytes)).convert("RGB")
    width, height = image.size

    x = int(max(0, min(width - 1, round(float(focus_x)))))
    y = int(max(0, min(height - 1, round(float(focus_y)))))
    r = int(max(20, radius))

    blurred = image.filter(ImageFilter.GaussianBlur(max(1, int(blur_radius))))
    mask = Image.new("L", (width, height), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((x - r, y - r, x + r, y + r), fill=255)

    composed = Image.composite(image, blurred, mask)
    draw = ImageDraw.Draw(composed)
    draw.ellipse((x - 18, y - 18, x + 18, y + 18), outline=(255, 216, 0), width=3)
    draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=(255, 216, 0), outline=(80, 60, 0), width=2)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    composed.save(out_path, "JPEG", quality=max(35, min(95, int(quality))), optimize=True)

    return {
        "width": width,
        "height": height,
        "focus": {"x": x, "y": y, "radius": r},
    }
