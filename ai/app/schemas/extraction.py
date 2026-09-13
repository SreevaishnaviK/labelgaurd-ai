"""AI service schemas (Phase 1 placeholders)."""
from pydantic import BaseModel


class PlaceholderResponse(BaseModel):
    status: str
    message: str
