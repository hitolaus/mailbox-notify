from __future__ import annotations

import asyncio
import unittest

from aiohue.v2.controllers.events import EventType

from cli.mock_hue_bridge import BUTTON_ID, CONTACT_ID, MockHueBridgeServer
from mailbox_notify.hue import AioHueClient, ConfigurableHueBridge
from mailbox_notify.state import HueEventType


class HueAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.server = MockHueBridgeServer(host="127.0.0.1", port=0, token="test-token")
        await self.server.start()

    async def asyncTearDown(self) -> None:
        await self.server.stop()

    async def test_connect_and_map_contact_and_button_events(self) -> None:
        client = AioHueClient(
            base_url=self.server.base_url,
            api_token="test-token",
            contact_id=CONTACT_ID,
            button_id=BUTTON_ID,
        )
        await client.connect()

        events = client.events()
        try:
            await self.server.emit_contact_opened()
            first = await asyncio.wait_for(anext(events), timeout=2)
            await self.server.emit_button_pressed()
            second = await asyncio.wait_for(anext(events), timeout=2)
        finally:
            await client.disconnect()

        self.assertEqual(first.kind, HueEventType.MAIL_DETECTED)
        self.assertEqual(second.kind, HueEventType.BUTTON_PRESSED)

    async def test_ignores_non_matching_resource_ids(self) -> None:
        client = AioHueClient(
            base_url=self.server.base_url,
            api_token="test-token",
            contact_id="different-contact-id",
            button_id="different-button-id",
        )
        await client.connect()

        events = client.events()
        try:
            await self.server.emit_contact_opened()
            await self.server.emit_button_pressed()
            with self.assertRaises(asyncio.TimeoutError):
                await asyncio.wait_for(anext(events), timeout=0.3)
        finally:
            await client.disconnect()

    async def test_disconnect_stops_event_iterator(self) -> None:
        client = AioHueClient(
            base_url=self.server.base_url,
            api_token="test-token",
            contact_id=CONTACT_ID,
            button_id=BUTTON_ID,
        )
        await client.connect()

        events = client.events()
        await client.disconnect()

        with self.assertRaises(StopAsyncIteration):
            await anext(events)


class ConfigurableHueBridgeTests(unittest.TestCase):
    def test_retains_http_base_url_for_mock_bridge(self) -> None:
        bridge = ConfigurableHueBridge("http://127.0.0.1:8000", "token")

        self.assertEqual(bridge.host, "127.0.0.1:8000")


class HueClientMappingTests(unittest.TestCase):
    def test_ignore_non_update_events(self) -> None:
        client = AioHueClient(
            base_url="http://127.0.0.1:8000",
            api_token="token",
            contact_id=CONTACT_ID,
            button_id=BUTTON_ID,
        )

        client._handle_contact_update(EventType.RESOURCE_ADDED, object())
        client._handle_button_update(EventType.RESOURCE_ADDED, object())

        self.assertTrue(client._events.empty())
