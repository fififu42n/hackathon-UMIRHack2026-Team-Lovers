import os

import numpy as np
from PIL import Image
from scipy import ndimage


def _find_marks(image):
    pixels = np.asarray(image.convert("RGB")).astype(int)
    red, blue = pixels[..., 0], pixels[..., 2]
    ink = (blue - red > 20) & (blue > 90)

    width = ink.shape[1]
    ink = ndimage.binary_dilation(ink, structure=np.ones((5, 21)))
    labels, _ = ndimage.label(ink)

    boxes = []
    for rows, cols in ndimage.find_objects(labels):
        boxes.append((cols.start, rows.start, cols.stop, rows.stop))

    seals = []
    for left, top, right, bottom in boxes:
        box_w, box_h = right - left, bottom - top
        if box_w > width * 0.09 and box_h > width * 0.09 and 0.6 < box_w / box_h < 1.6:
            seals.append((left, top, right, bottom))

    signature = False
    for left, top, right, bottom in boxes:
        box_w, box_h = right - left, bottom - top
        center_x, center_y = (left + right) / 2, (top + bottom) / 2
        inside_seal = any(s[0] <= center_x <= s[2] and s[1] <= center_y <= s[3] for s in seals)
        if not inside_seal and box_w > width * 0.08 and box_w > box_h * 1.5:
            signature = True

    return signature, len(seals) > 0


def _load_pages(file_path):
    if os.path.splitext(file_path)[1].lower() == ".pdf":
        import pymupdf

        pages = []
        with pymupdf.open(file_path) as pdf:
            for page in pdf:
                pix = page.get_pixmap(dpi=150)
                pages.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
        return pages
    return [Image.open(file_path)]


def detect_marks(file_path):
    has_signature = False
    has_seal = False
    for page in _load_pages(file_path):
        signature, seal = _find_marks(page)
        has_signature = has_signature or signature
        has_seal = has_seal or seal
    return has_signature, has_seal