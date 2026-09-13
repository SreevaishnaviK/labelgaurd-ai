"""OCR text utilities shared by extractors."""


def block_sort_key(block):
    """Reading-order key for OCR blocks: page, then top, then left."""
    bbox = block.bbox or {}
    return (block.page_number, bbox.get("y", 0), bbox.get("x", 0))


def sort_blocks(blocks):
    return sorted(blocks, key=block_sort_key)


def blocks_full_text(blocks) -> str:
    """Join block texts in reading order with line breaks."""
    return "\n".join(block.text for block in sort_blocks(blocks))
