"""Mailbox notification state machine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from .pixoo import PixooDisplay


class HueEventType(Enum):
    """Normalized Hue events used by the app."""

    MAIL_DETECTED = auto()
    BUTTON_PRESSED = auto()


@dataclass(frozen=True)
class HueEvent:
    """Internal event emitted by the Hue adapter."""

    kind: HueEventType


@dataclass
class MailboxStateMachine:
    """Track whether new mail is currently visible."""

    mail_present: bool = False

    async def handle(self, event: HueEvent, display: PixooDisplay) -> None:
        if event.kind is HueEventType.MAIL_DETECTED:
            if not self.mail_present:
                self.mail_present = True
                await display.show_new_mail()
            return

        if event.kind is HueEventType.BUTTON_PRESSED and self.mail_present:
            self.mail_present = False
            await display.clear()
