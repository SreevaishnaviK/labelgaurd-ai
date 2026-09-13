"""EXIF orientation correction.

Uses Pillow's ImageOps.exif_transpose which reads the EXIF orientation tag
once and transposes accordingly, then strips the tag — so applying it twice
is a no-op (no double rotation).
"""
from PIL import Image, ImageOps


def correct_orientation(image: Image.Image) -> Image.Image:
    """Return the image with EXIF orientation applied (idempotent).

    Images without orientation metadata pass through unchanged.
    """
    transposed = ImageOps.exif_transpose(image)
    # exif_transpose strips the orientation tag; on images without it the
    # same instance comes back, which is fine.
    return transposed if transposed is not None else image
