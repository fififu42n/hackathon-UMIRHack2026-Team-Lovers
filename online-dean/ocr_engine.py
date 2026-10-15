import os

import numpy as np
from PIL import Image
from scipy import ndimage

_reader = None


def get_reader():
    """easyocr грузится при первом распознавании, а не при импорте модуля."""
    global _reader
    if _reader is None:
        import easyocr
        _reader = easyocr.Reader(["ru", "en"], gpu=False)
    return _reader

PROFILES = {
    "fast": {"min_size": 5, "text_threshold": 0.4, "low_text": 0.25},
    "accurate": {"min_size": 5, "mag_ratio": 1.75},
}
OCR_OPTIONS = PROFILES["fast"]
SHRINK_PAGE = True
USE_PDF_TEXT_LAYER = False


def prepare_image(image):
    pixels = np.asarray(image.convert("RGB")).copy()
    if not SHRINK_PAGE:
        return pixels

    blue = (pixels[..., 2].astype(int) - pixels[..., 0].astype(int) > 20) & (pixels[..., 2] > 90)
    pixels[ndimage.binary_dilation(blue, iterations=2)] = 255

    dark = pixels.min(axis=2) < 200
    keep_rows = ndimage.binary_dilation(dark.any(axis=1), structure=np.ones(40))
    if not keep_rows.any():
        return pixels
    pixels = pixels[keep_rows]
    dark = dark[keep_rows]

    columns = np.nonzero(dark.any(axis=0))[0]
    left = max(columns.min() - 40, 0)
    right = columns.max() + 40
    return pixels[:, left:right]


def _read_lines(image):
    results = get_reader().readtext(image, **OCR_OPTIONS)
    items = []
    for box, text, confidence in results:
        xs = [point[0] for point in box]
        ys = [point[1] for point in box]
        items.append({
            "x": min(xs),
            "y": (min(ys) + max(ys)) / 2,
            "h": max(ys) - min(ys),
            "text": text,
        })

    items.sort(key=lambda item: item["y"])

    lines = []
    for item in items:
        if lines and abs(item["y"] - lines[-1]["y"]) < item["h"] * 0.6:
            lines[-1]["items"].append(item)
        else:
            lines.append({"y": item["y"], "items": [item]})

    result_lines = []
    for line in lines:
        ordered = sorted(line["items"], key=lambda item: item["x"])
        result_lines.append(" ".join(item["text"] for item in ordered))
    return "\n".join(result_lines)


def recognize(file_path):
    if os.path.splitext(file_path)[1].lower() == ".pdf":
        import pymupdf
        with pymupdf.open(file_path) as pdf:
            if USE_PDF_TEXT_LAYER:
                text = "\n".join(page.get_text() for page in pdf)
                if len(text.strip()) > 50:
                    return text
            pages = []
            for page in pdf:
                pix = page.get_pixmap(dpi=137)
                image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                pages.append(_read_lines(prepare_image(image)))
        return "\n".join(pages)
    return _read_lines(prepare_image(Image.open(file_path)))