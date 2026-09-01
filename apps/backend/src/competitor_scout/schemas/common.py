from pydantic import BaseModel


class CursorPage[T](BaseModel):
    items: list[T]
    next_cursor: str | None
