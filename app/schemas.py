from typing import Literal

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    user_id: int = 1
    approach: Literal["agent", "rag"] = "agent"


class Citation(BaseModel):
    """Provenance for an answer fragment: a KB chunk or a SQL tool call."""
    kind: Literal["kb_chunk", "sql_tool"]
    ref: str          # chunk id / document title, or tool name with arguments
    detail: str = ""  # e.g. "42 transactions between 2026-06-01 and 2026-06-30"


class AskResponse(BaseModel):
    answer: str
    approach: Literal["agent", "rag"]
    refused: bool = False
    citations: list[Citation] = []
