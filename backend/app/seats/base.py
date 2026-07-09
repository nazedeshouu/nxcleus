"""Seam between the engine (backend) and the seat layer (AI engineer).
Seat modules import ONLY from this file (+ app.db.models for artifact shapes)."""
from typing import Any, Awaitable, Callable, Literal, Protocol

from pydantic import BaseModel

Role = Literal["system", "user", "assistant"]
DataClass = Literal["RAW", "SANITIZED"]


class Message(BaseModel):
    role: Role
    content: str


class Completion(BaseModel):
    text: str
    parsed: dict[str, Any] | None = None   # set when schema was provided
    usage: dict[str, int] = {}             # tokens_in, tokens_out


class CompleteFn(Protocol):
    """router.complete curried with seat's scope + metering by the engine."""
    async def __call__(
        self, seat: str, messages: list[Message], *,
        data_class: DataClass,
        schema: dict | None = None,
        stream: Callable[[str], Awaitable[None]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Completion: ...


EmitFn = Callable[[str, dict], Awaitable[None]]   # (event_type, payload) -> emitted
