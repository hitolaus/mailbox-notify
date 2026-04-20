from __future__ import annotations

import asyncio
import io
import json
import logging
import sys
import unittest

from aiohttp import ClientSession

from cli.mock_hue_bridge import (
    BUTTON_ID,
    CONTACT_ID,
    DEVICE_ID,
    MockHueBridgeServer,
    RawTerminalWriter,
    build_full_state,
    build_button_pressed_event,
    build_contact_opened_event,
    encode_sse_event,
    raw_terminal_output,
)


class MockHueBridgeEventTests(unittest.TestCase):
    def test_raw_terminal_writer_translates_newlines(self) -> None:
        stream = io.StringIO()
        writer = RawTerminalWriter(stream)

        writer.write("one\ntwo\n")

        self.assertEqual(stream.getvalue(), "one\r\ntwo\r\n\r")

    def test_raw_terminal_output_patches_existing_stream_handlers(self) -> None:
        original_stderr = sys.stderr
        logger = logging.getLogger("tests.raw-terminal-output")
        logger.handlers = []
        logger.propagate = False
        handler = logging.StreamHandler(original_stderr)
        logger.addHandler(handler)

        try:
            with raw_terminal_output():
                self.assertIsNot(handler.stream, original_stderr)
        finally:
            logger.removeHandler(handler)
            handler.close()

    def test_build_contact_opened_event_shape(self) -> None:
        event = build_contact_opened_event()

        self.assertEqual(event["type"], "update")
        self.assertEqual(event["data"][0]["id"], CONTACT_ID)
        self.assertEqual(event["data"][0]["type"], "contact")
        self.assertEqual(event["data"][0]["contact_report"]["state"], "contact")

    def test_build_button_pressed_event_shape(self) -> None:
        event = build_button_pressed_event()

        self.assertEqual(event["type"], "update")
        self.assertEqual(event["data"][0]["id"], BUTTON_ID)
        self.assertEqual(event["data"][0]["type"], "button")
        self.assertEqual(
            event["data"][0]["button"]["button_report"]["event"],
            "initial_press",
        )

    def test_encode_sse_event_wraps_event_in_json_array(self) -> None:
        event = build_contact_opened_event()

        payload = encode_sse_event(event).decode()

        self.assertIn(f"id: {event['id']}\n", payload)
        self.assertTrue(payload.endswith("\n\n"))
        data_line = next(
            line for line in payload.splitlines() if line.startswith("data: ")
        )
        self.assertEqual(json.loads(data_line[6:]), [event])

    def test_build_full_state_contains_required_resources(self) -> None:
        full_state = build_full_state()

        self.assertEqual(
            [item["type"] for item in full_state],
            ["device", "contact", "button"],
        )
        self.assertEqual(full_state[0]["id"], DEVICE_ID)


class MockHueBridgeServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.server = MockHueBridgeServer(host="127.0.0.1", port=0, token="test-token")
        await self.server.start()
        self.session = ClientSession(headers={"hue-application-key": "test-token"})

    async def asyncTearDown(self) -> None:
        await self.session.close()
        await self.server.stop()

    async def _open_eventstream(self):
        response = await self.session.get(f"{self.server.base_url}/eventstream/clip/v2")
        await response.content.readline()
        await response.content.readline()
        return response

    async def test_resource_endpoints_return_fixed_mock_resources(self) -> None:
        device_response = await self.session.get(
            f"{self.server.base_url}/clip/v2/resource/device"
        )
        contact_response = await self.session.get(
            f"{self.server.base_url}/clip/v2/resource/contact"
        )
        button_response = await self.session.get(
            f"{self.server.base_url}/clip/v2/resource/button"
        )
        full_state_response = await self.session.get(
            f"{self.server.base_url}/clip/v2/resource"
        )

        self.assertEqual(device_response.status, 200)
        self.assertEqual(contact_response.status, 200)
        self.assertEqual(button_response.status, 200)
        self.assertEqual(full_state_response.status, 200)

        device_payload = await device_response.json()
        contact_payload = await contact_response.json()
        button_payload = await button_response.json()
        full_state_payload = await full_state_response.json()

        self.assertEqual(device_payload["data"][0]["id"], DEVICE_ID)
        self.assertEqual(contact_payload["data"][0]["id"], CONTACT_ID)
        self.assertEqual(button_payload["data"][0]["id"], BUTTON_ID)
        self.assertEqual(len(full_state_payload["data"]), 3)

    async def test_eventstream_rejects_invalid_token(self) -> None:
        async with ClientSession() as session:
            response = await session.get(f"{self.server.base_url}/eventstream/clip/v2")
            self.assertEqual(response.status, 403)
            await response.release()

    async def test_eventstream_broadcasts_contact_event(self) -> None:
        response = await self._open_eventstream()

        emit_task = asyncio.create_task(self.server.emit_contact_opened())
        event_id_line = await asyncio.wait_for(response.content.readline(), timeout=2)
        data_line = await asyncio.wait_for(response.content.readline(), timeout=2)
        await asyncio.wait_for(emit_task, timeout=2)

        self.assertTrue(event_id_line.decode().startswith("id: "))
        self.assertTrue(data_line.decode().startswith("data: "))

        payload = json.loads(data_line.decode()[6:].strip())
        self.assertEqual(payload[0]["data"][0]["type"], "contact")

        response.close()

    async def test_eventstream_broadcasts_multiple_events_in_order(self) -> None:
        response = await self._open_eventstream()

        first = await self.server.emit_contact_opened()
        second = await self.server.emit_button_pressed()

        await asyncio.wait_for(response.content.readline(), timeout=2)
        first_data = await asyncio.wait_for(response.content.readline(), timeout=2)
        await asyncio.wait_for(response.content.readline(), timeout=2)
        await asyncio.wait_for(response.content.readline(), timeout=2)
        second_data = await asyncio.wait_for(response.content.readline(), timeout=2)

        first_payload = json.loads(first_data.decode()[6:].strip())
        second_payload = json.loads(second_data.decode()[6:].strip())

        self.assertEqual(first_payload[0]["id"], first["id"])
        self.assertEqual(second_payload[0]["id"], second["id"])
        self.assertEqual(second_payload[0]["data"][0]["type"], "button")

        response.close()
