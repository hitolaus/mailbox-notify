from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from mailbox_notify.app import main, run, serve
from mailbox_notify.config import Config
from mailbox_notify.hue import button_pressed, mail_detected
from mailbox_notify.pixoo import StubPixooDisplay
from mailbox_notify.state import MailboxStateMachine


class FakeHueClient:
    def __init__(self, events):
        self._events = list(events)
        self.connected = False

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def events(self):
        for event in self._events:
            yield event


class AppServeTests(unittest.IsolatedAsyncioTestCase):
    async def test_serve_drives_display_from_hue_events(self) -> None:
        hue = FakeHueClient([mail_detected(), button_pressed()])
        display = StubPixooDisplay()
        state = MailboxStateMachine()

        with self.assertLogs("mailbox_notify.app", level="INFO") as logs:
            await serve(hue, display, state)

        self.assertEqual(display.calls, ["show_new_mail", "clear"])
        self.assertFalse(state.mail_present)
        self.assertEqual(
            logs.output,
            [
                "INFO:mailbox_notify.app:Received Hue event: MAIL_DETECTED",
                "INFO:mailbox_notify.app:Received Hue event: BUTTON_PRESSED",
            ],
        )


class AppMainTests(unittest.TestCase):
    def test_run_builds_hue_client_from_config(self) -> None:
        fake_config = Config(
            hue_base_url="http://127.0.0.1:8000",
            hue_api_token="token",
            hue_contact_id="contact-id",
            hue_button_id="button-id",
            pixoo_host="",
        )

        async def assert_client(*args, **kwargs):
            hue_client = args[0]
            self.assertEqual(hue_client.base_url, fake_config.hue_base_url)
            self.assertEqual(hue_client.api_token, fake_config.hue_api_token)
            self.assertEqual(hue_client.contact_id, fake_config.hue_contact_id)
            self.assertEqual(hue_client.button_id, fake_config.hue_button_id)
            raise asyncio.CancelledError

        with (
            patch("mailbox_notify.app.load_config", return_value=fake_config),
            patch(
                "mailbox_notify.app.serve",
                side_effect=assert_client,
            ),
        ):
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(run())

    def test_main_suppresses_keyboard_interrupt(self) -> None:
        def raise_keyboard_interrupt(coro):
            coro.close()
            raise KeyboardInterrupt

        with patch(
            "mailbox_notify.app.asyncio.run",
            side_effect=raise_keyboard_interrupt,
        ):
            main()
