"""Pixoo64 adapter stubs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class PixooDisplay(Protocol):
    async def show_new_mail(self) -> None: ...

    async def clear(self) -> None: ...


@dataclass
class StubPixooDisplay(PixooDisplay):
    """In-memory display stub used by the app and tests."""

    calls: list[str] = field(default_factory=list)

    async def show_new_mail(self) -> None:
        self.calls.append("show_new_mail")

    async def clear(self) -> None:
        self.calls.append("clear")
