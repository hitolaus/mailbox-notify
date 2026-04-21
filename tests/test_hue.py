from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from aiohue.v2.controllers.events import EventType

from cli.mock_hue_bridge import BUTTON_ID, CONTACT_ID, MockHueBridgeServer
from mailbox_notify.hue import (
    AioHueClient,
    ConfigurableHueBridge,
    HueDiscoveryError,
    HueTokenCreationError,
    create_hue_application_key,
    discover_hue_buttons,
    discover_hue_contacts,
)
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


class HueTokenCreationTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_hue_application_key_returns_token(self) -> None:
        payload = [{"success": {"username": "token-123", "clientkey": "client-456"}}]

        class FakeResponse:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            def raise_for_status(self) -> None:
                return None

            async def json(self):
                return payload

        class FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            def post(self, url, json, ssl):
                return FakeResponse()

        with patch(
            "mailbox_notify.hue.aiohttp.ClientSession", return_value=FakeSession()
        ):
            created = await create_hue_application_key("https://10.0.0.20")

        self.assertEqual(created, {"token": "token-123", "clientkey": "client-456"})

    async def test_create_hue_application_key_surfaces_bridge_error(self) -> None:
        payload = [{"error": {"description": "link button not pressed"}}]

        class FakeResponse:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            def raise_for_status(self) -> None:
                return None

            async def json(self):
                return payload

        class FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            def post(self, url, json, ssl):
                return FakeResponse()

        with patch(
            "mailbox_notify.hue.aiohttp.ClientSession", return_value=FakeSession()
        ):
            with self.assertRaises(HueTokenCreationError) as error:
                await create_hue_application_key("https://10.0.0.20")

        self.assertEqual(str(error.exception), "link button not pressed")


class HueResourceDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_discover_hue_contacts_uses_device_names(self) -> None:
        payloads = [
            {"data": [{"id": "contact-id-1", "owner": {"rid": "device-id-1"}}]},
            {"data": []},
            {"data": [{"id": "device-id-1", "metadata": {"name": "Mailbox Sensor"}}]},
        ]

        with patch(
            "mailbox_notify.hue.aiohttp.ClientSession",
            return_value=_build_fake_client_session(payloads),
        ):
            contacts = await discover_hue_contacts("https://10.0.0.20", "token")

        self.assertEqual(
            contacts,
            [
                {
                    "id": "contact-id-1",
                    "name": "Mailbox Sensor",
                    "owner_rid": "device-id-1",
                }
            ],
        )

    async def test_discover_hue_contacts_orders_by_name(self) -> None:
        payloads = [
            {
                "data": [
                    {"id": "contact-id-1", "owner": {"rid": "device-id-1"}},
                    {"id": "contact-id-2", "owner": {"rid": "device-id-2"}},
                ]
            },
            {"data": []},
            {
                "data": [
                    {"id": "device-id-1", "metadata": {"name": "Zulu Sensor"}},
                    {"id": "device-id-2", "metadata": {"name": "Alpha Sensor"}},
                ]
            },
        ]

        with patch(
            "mailbox_notify.hue.aiohttp.ClientSession",
            return_value=_build_fake_client_session(payloads),
        ):
            contacts = await discover_hue_contacts("https://10.0.0.20", "token")

        self.assertEqual(
            [contact["name"] for contact in contacts], ["Alpha Sensor", "Zulu Sensor"]
        )

    async def test_discover_hue_buttons_includes_control_id(self) -> None:
        payloads = [
            {"data": []},
            {
                "data": [
                    {
                        "id": "button-id-1",
                        "owner": {"rid": "device-id-1"},
                        "metadata": {"control_id": 1},
                    }
                ]
            },
            {
                "data": [
                    {"id": "device-id-1", "metadata": {"name": "Mailbox Clear Button"}}
                ]
            },
        ]

        with patch(
            "mailbox_notify.hue.aiohttp.ClientSession",
            return_value=_build_fake_client_session(payloads),
        ):
            buttons = await discover_hue_buttons("https://10.0.0.20", "token")

        self.assertEqual(
            buttons,
            [
                {
                    "id": "button-id-1",
                    "name": "Mailbox Clear Button",
                    "owner_rid": "device-id-1",
                    "control_id": "1",
                }
            ],
        )

    async def test_discover_hue_buttons_order_by_name(self) -> None:
        payloads = [
            {"data": []},
            {
                "data": [
                    {
                        "id": "button-id-1",
                        "owner": {"rid": "device-id-1"},
                        "metadata": {"control_id": 1},
                    },
                    {
                        "id": "button-id-2",
                        "owner": {"rid": "device-id-2"},
                        "metadata": {"control_id": 2},
                    },
                ]
            },
            {
                "data": [
                    {"id": "device-id-1", "metadata": {"name": "Zulu Button"}},
                    {"id": "device-id-2", "metadata": {"name": "Alpha Button"}},
                ]
            },
        ]

        with patch(
            "mailbox_notify.hue.aiohttp.ClientSession",
            return_value=_build_fake_client_session(payloads),
        ):
            buttons = await discover_hue_buttons("https://10.0.0.20", "token")

        self.assertEqual(
            [button["name"] for button in buttons], ["Alpha Button", "Zulu Button"]
        )

    async def test_discover_hue_contacts_requires_token(self) -> None:
        with self.assertRaises(HueDiscoveryError) as error:
            await discover_hue_contacts("https://10.0.0.20", "")

        self.assertEqual(str(error.exception), "Enter a Hue API Token first.")


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


def _build_fake_client_session(payloads: list[dict]):
    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def raise_for_status(self) -> None:
            return None

        async def json(self):
            return self._payload

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def get(self, url, headers, ssl):
            return FakeResponse(payloads.pop(0))

    return FakeSession()
