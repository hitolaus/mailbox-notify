from __future__ import annotations

import unittest

from mailbox_notify.hue import button_pressed, mail_detected
from mailbox_notify.pixoo import StubPixooDisplay
from mailbox_notify.state import MailboxStateMachine


class StateMachineTests(unittest.IsolatedAsyncioTestCase):
    async def test_mail_and_clear_transitions(self) -> None:
        state = MailboxStateMachine()
        display = StubPixooDisplay()

        await state.handle(mail_detected(), display)
        await state.handle(mail_detected(), display)
        await state.handle(button_pressed(), display)
        await state.handle(button_pressed(), display)

        self.assertFalse(state.mail_present)
        self.assertEqual(display.calls, ["show_new_mail", "clear"])
