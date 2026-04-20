from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from mailbox_notify.pixoo import (
    PixooClient,
    create_pixoo_display,
    discover_pixoo_devices,
)


class FakePixooDevice:
    def __init__(self, ip_address: str | None = None) -> None:
        self.ip_address = ip_address
        self.calls: list[tuple] = []

    def fill(self, rgb=(0, 0, 0)) -> None:
        self.calls.append(("fill", rgb))

    def draw_text(self, text, xy=(0, 0), rgb=(255, 255, 255)) -> None:
        self.calls.append(("draw_text", text, xy, rgb))

    def draw_line(self, start_xy, stop_xy, rgb=(255, 255, 255)) -> None:
        self.calls.append(("draw_line", start_xy, stop_xy, rgb))

    def draw_filled_rectangle(
        self,
        top_left_xy=(0, 0),
        bottom_right_xy=(1, 1),
        rgb=(255, 255, 255),
    ) -> None:
        self.calls.append(("draw_filled_rectangle", top_left_xy, bottom_right_xy, rgb))

    def clear(self) -> None:
        self.calls.append(("clear",))

    def push(self) -> None:
        self.calls.append(("push",))


class PixooClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_show_new_mail_starts_looping_animation(self) -> None:
        device = FakePixooDevice("10.0.0.5")
        client = PixooClient(device, "10.0.0.5")

        await client.show_new_mail()
        await asyncio.sleep(0.15)
        await client.clear()

        push_count = sum(1 for call in device.calls if call == ("push",))
        self.assertGreaterEqual(push_count, 2)
        self.assertTrue(any(call[0] == "draw_line" for call in device.calls))
        self.assertTrue(
            any(call[0] == "draw_filled_rectangle" for call in device.calls)
        )
        self.assertTrue(
            any(call[:2] == ("draw_text", "New Mail") for call in device.calls)
        )

    async def test_clear_pushes_black_screen(self) -> None:
        device = FakePixooDevice("10.0.0.5")
        client = PixooClient(device, "10.0.0.5")

        await client.clear()

        self.assertEqual(device.calls, [("clear",), ("push",)])

    async def test_repeated_show_new_mail_does_not_start_duplicate_loops(self) -> None:
        device = FakePixooDevice("10.0.0.5")
        client = PixooClient(device, "10.0.0.5")

        await client.show_new_mail()
        first_task = client._animation_task
        await client.show_new_mail()
        second_task = client._animation_task
        await client.clear()

        self.assertIs(first_task, second_task)


class PixooFactoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_discover_pixoo_devices_returns_normalized_entries(self) -> None:
        payload = {
            "ReturnCode": 0,
            "DeviceList": [
                {
                    "DeviceName": "Pixoo64",
                    "DevicePrivateIP": "10.0.0.47",
                    "DeviceId": 300247395,
                    "DeviceMac": "2cbcbb116a0c",
                    "Hardware": 92,
                }
            ],
        }

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

            def post(self, url):
                return FakeResponse()

        with patch(
            "mailbox_notify.pixoo.aiohttp.ClientSession", return_value=FakeSession()
        ):
            devices = await discover_pixoo_devices()

        self.assertEqual(
            devices,
            [
                {
                    "name": "Pixoo64",
                    "host": "10.0.0.47",
                    "device_id": "300247395",
                    "device_mac": "2cbcbb116a0c",
                    "hardware": "92",
                }
            ],
        )

    async def test_pixoo_host_skips_discovery(self) -> None:
        device = FakePixooDevice("10.0.0.9")

        with (
            patch(
                "mailbox_notify.pixoo._build_pixoo_device", return_value=device
            ) as build,
            patch(
                "mailbox_notify.pixoo._discover_lan_pixoo_host",
                new=AsyncMock(),
            ) as discover,
        ):
            client = await create_pixoo_display("10.0.0.9")

        self.assertEqual(client.host, "10.0.0.9")
        build.assert_called_once_with("10.0.0.9")
        discover.assert_not_called()

    async def test_uses_library_auto_discovery_when_available(self) -> None:
        device = FakePixooDevice("10.0.0.10")

        with (
            patch(
                "mailbox_notify.pixoo._build_pixoo_device", return_value=device
            ) as build,
            patch(
                "mailbox_notify.pixoo._discover_lan_pixoo_host",
                new=AsyncMock(),
            ) as discover,
        ):
            client = await create_pixoo_display("")

        self.assertEqual(client.host, "10.0.0.10")
        build.assert_called_once_with(None)
        discover.assert_not_called()

    async def test_falls_back_to_divoom_discovery(self) -> None:
        fallback_device = FakePixooDevice("10.0.0.11")

        with (
            patch(
                "mailbox_notify.pixoo._build_pixoo_device",
                side_effect=[RuntimeError("library discovery failed"), fallback_device],
            ) as build,
            patch(
                "mailbox_notify.pixoo._discover_lan_pixoo_host",
                new=AsyncMock(return_value="10.0.0.11"),
            ) as discover,
        ):
            client = await create_pixoo_display("")

        self.assertEqual(client.host, "10.0.0.11")
        self.assertEqual(build.call_args_list[0].args, (None,))
        self.assertEqual(build.call_args_list[1].args, ("10.0.0.11",))
        discover.assert_awaited_once()
