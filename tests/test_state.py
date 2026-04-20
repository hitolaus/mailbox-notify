from __future__ import annotations

import unittest

from mailbox_notify.hue import button_pressed, mail_detected
from mailbox_notify.state import MailboxStateMachine


class FakePixooDisplay:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def show_new_mail(self) -> None:
        self.calls.append("show_new_mail")

    async def clear(self) -> None:
        self.calls.append("clear")


class StateMachineTests(unittest.IsolatedAsyncioTestCase):
    async def test_mail_and_clear_transitions(self) -> None:
        state = MailboxStateMachine()
        display = FakePixooDisplay()

        await state.handle(mail_detected(), display)
        await state.handle(mail_detected(), display)
        await state.handle(button_pressed(), display)
        await state.handle(button_pressed(), display)

        self.assertFalse(state.mail_present)
        self.assertEqual(display.calls, ["show_new_mail", "clear"])
