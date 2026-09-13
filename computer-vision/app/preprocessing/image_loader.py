"""Safe image loading.

Loads raw bytes into Pillow images without executing anything from the
file content. PDFs are rasterized page-by-page via pdf2image/poppler.
"""
import io

from PIL import Image

# Safety cap for decompressed images (guard against decompression bombs).
MAX_PIXELS = 40_000_000  # ~40 MP

Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def decode_image(data: bytes) -> Image.Image:
    """Decode PNG/JPEG bytes into a Pillow image. Raises ValueError if unreadable."""
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as exc:
        raise ValueError(f"File is not a readable image: {exc}") from exc
    if image.width * image.height > MAX_PIXELS:
        raise ValueError("Image dimensions exceed the supported limit.")
    return image


def decode_pdf(data: bytes, dpi: int = 200) -> list[Image.Image]:
    """Rasterize PDF bytes into one Pillow image per page (1-indexed order)."""
    from pdf2image import convert_from_bytes

    try:
        pages = convert_from_bytes(data, dpi=dpi)
    except Exception as exc:
        raise ValueError(f"PDF could not be converted: {exc}") from exc
    if not pages:
        raise ValueError("PDF contains no pages.")
    return pages
