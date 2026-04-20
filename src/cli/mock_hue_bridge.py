"""Interactive mock Philips Hue Bridge event stream server."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
import io
import json
import logging
import sys
import termios
import tty
from typing import Any
from uuid import uuid4

from aiohttp import web


LOGGER = logging.getLogger(__name__)

DEVICE_ID = "mock-device-id"
CONTACT_ID = "mock-contact-id"
BUTTON_ID = "mock-button-id"


class RawTerminalWriter(io.TextIOBase):
    """Translate LF to CRLF while stdin is in raw mode."""

    def __init__(self, stream: io.TextIOBase) -> None:
        self._stream = stream

    def write(self, text: str) -> int:
        translated = text.replace("\n", "\r\n")
        if translated.endswith("\r\n"):
            translated += "\r"
        return self._stream.write(translated)

    def flush(self) -> None:
        self._stream.flush()

    def isatty(self) -> bool:
        return self._stream.isatty()

    @property
    def encoding(self) -> str:
        return self._stream.encoding


@contextmanager
def raw_terminal_output():
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    wrapped_stdout = RawTerminalWriter(original_stdout)
    wrapped_stderr = RawTerminalWriter(original_stderr)
    sys.stdout = wrapped_stdout
    sys.stderr = wrapped_stderr
    patched_handlers = _patch_logging_handlers(
        original_stdout,
        original_stderr,
        wrapped_stdout,
        wrapped_stderr,
    )
    try:
        yield
    finally:
        for handler, stream in patched_handlers:
            handler.stream = stream
        sys.stdout = original_stdout
        sys.stderr = original_stderr


def _patch_logging_handlers(
    original_stdout: io.TextIOBase,
    original_stderr: io.TextIOBase,
    wrapped_stdout: RawTerminalWriter,
    wrapped_stderr: RawTerminalWriter,
) -> list[tuple[logging.StreamHandler, io.TextIOBase]]:
    patched_handlers: list[tuple[logging.StreamHandler, io.TextIOBase]] = []

    for logger in _iter_loggers():
        for handler in logger.handlers:
            if not isinstance(handler, logging.StreamHandler):
                continue
            if handler.stream is original_stdout:
                patched_handlers.append((handler, handler.stream))
                handler.stream = wrapped_stdout
            elif handler.stream is original_stderr:
                patched_handlers.append((handler, handler.stream))
                handler.stream = wrapped_stderr

    return patched_handlers


def _iter_loggers() -> list[logging.Logger]:
    loggers: list[logging.Logger] = [logging.getLogger()]
    for logger in logging.root.manager.loggerDict.values():
        if isinstance(logger, logging.Logger):
            loggers.append(logger)
    return loggers


def utc_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_contact_resource() -> dict[str, Any]:
    return {
        "id": CONTACT_ID,
        "type": "contact",
        "owner": {"rid": DEVICE_ID, "rtype": "device"},
        "enabled": True,
        "contact_report": None,
    }


def build_button_resource() -> dict[str, Any]:
    return {
        "id": BUTTON_ID,
        "type": "button",
        "owner": {"rid": DEVICE_ID, "rtype": "device"},
        "metadata": {"control_id": 1},
        "button": None,
    }


def build_device_resource() -> dict[str, Any]:
    return {
        "id": DEVICE_ID,
        "type": "device",
        "product_data": {
            "model_id": "MOCK-HUE-BRIDGE",
            "manufacturer_name": "mailbox-notify",
            "product_name": "Mock Hue Bridge Device",
            "product_archetype": "bridge_v2",
            "certified": False,
            "software_version": "0.1.0",
        },
        "metadata": {
            "name": "Mock Hue Bridge Device",
            "archetype": "bridge_v2",
        },
        "services": [
            {"rid": CONTACT_ID, "rtype": "contact"},
            {"rid": BUTTON_ID, "rtype": "button"},
        ],
    }


def build_full_state() -> list[dict[str, Any]]:
    return [build_device_resource(), build_contact_resource(), build_button_resource()]


def build_contact_opened_event() -> dict[str, Any]:
    timestamp = utc_timestamp()
    return {
        "creationtime": timestamp,
        "id": str(uuid4()),
        "type": "update",
        "data": [
            {
                **build_contact_resource(),
                "contact_report": {
                    "changed": timestamp,
                    "state": "contact",
                },
            }
        ],
    }


def build_button_pressed_event() -> dict[str, Any]:
    timestamp = utc_timestamp()
    return {
        "creationtime": timestamp,
        "id": str(uuid4()),
        "type": "update",
        "data": [
            {
                **build_button_resource(),
                "button": {
                    "button_report": {
                        "event": "initial_press",
                        "updated": timestamp,
                    }
                },
            }
        ],
    }


def encode_sse_event(event: dict[str, Any]) -> bytes:
    payload = json.dumps([event], separators=(",", ":"))
    return f"id: {event['id']}\ndata: {payload}\n\n".encode()


@dataclass(eq=False)
class StreamClient:
    response: web.StreamResponse
    queue: asyncio.Queue[bytes | None] = field(default_factory=asyncio.Queue)


class MockHueBridgeServer:
    def __init__(self, host: str, port: int, token: str) -> None:
        self.host = host
        self.port = port
        self.token = token
        self._clients: set[StreamClient] = set()
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._app = web.Application()
        self._app.router.add_get("/eventstream/clip/v2", self.handle_eventstream)
        self._app.router.add_get(
            "/clip/v2/resource/device", self.handle_device_resource
        )
        self._app.router.add_get(
            "/clip/v2/resource/contact", self.handle_contact_resource
        )
        self._app.router.add_get(
            "/clip/v2/resource/button", self.handle_button_resource
        )
        self._app.router.add_get("/clip/v2/resource", self.handle_full_state)

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    async def start(self) -> None:
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        sockets = getattr(self._site._server, "sockets", None)
        if sockets:
            self.port = sockets[0].getsockname()[1]

    async def stop(self) -> None:
        clients = list(self._clients)
        for client in clients:
            await client.queue.put(None)
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
            self._site = None

    async def emit_contact_opened(self) -> dict[str, Any]:
        event = build_contact_opened_event()
        await self.broadcast(event)
        return event

    async def emit_button_pressed(self) -> dict[str, Any]:
        event = build_button_pressed_event()
        await self.broadcast(event)
        return event

    async def broadcast(self, event: dict[str, Any]) -> None:
        payload = encode_sse_event(event)
        clients = list(self._clients)
        for client in clients:
            await client.queue.put(payload)

    async def handle_eventstream(self, request: web.Request) -> web.StreamResponse:
        if self.token and request.headers.get("hue-application-key") != self.token:
            raise web.HTTPForbidden(text="invalid hue application key")

        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
        await response.prepare(request)
        client = StreamClient(response=response)
        self._clients.add(client)

        try:
            await response.write(b": connected\n\n")
            while True:
                payload = await client.queue.get()
                if payload is None:
                    break
                await response.write(payload)
        except (ConnectionResetError, RuntimeError):
            LOGGER.debug("Eventstream client disconnected")
        finally:
            self._clients.discard(client)
            with suppress(ConnectionResetError, RuntimeError):
                await response.write_eof()

        return response

    async def handle_device_resource(self, request: web.Request) -> web.Response:
        self._check_token(request)
        return web.json_response({"data": [build_device_resource()], "errors": []})

    async def handle_contact_resource(self, request: web.Request) -> web.Response:
        self._check_token(request)
        return web.json_response({"data": [build_contact_resource()], "errors": []})

    async def handle_button_resource(self, request: web.Request) -> web.Response:
        self._check_token(request)
        return web.json_response({"data": [build_button_resource()], "errors": []})

    async def handle_full_state(self, request: web.Request) -> web.Response:
        self._check_token(request)
        return web.json_response({"data": build_full_state(), "errors": []})

    def _check_token(self, request: web.Request) -> None:
        if self.token and request.headers.get("hue-application-key") != self.token:
            raise web.HTTPForbidden(text="invalid hue application key")


async def run_keyboard_loop(server: MockHueBridgeServer) -> None:
    fd = sys.stdin.fileno()
    previous = termios.tcgetattr(fd)
    tty.setraw(fd)

    try:
        with raw_terminal_output():
            print(
                "Controls: [o] contact opened, [b] button pressed, [q] quit, Ctrl+C to exit"
            )
            while True:
                char = await asyncio.to_thread(sys.stdin.read, 1)
                if char in {"\x03", "q"}:
                    raise KeyboardInterrupt
                if char == "o":
                    event = await server.emit_contact_opened()
                    print(f"Sent contact opened: {event['id']}")
                elif char == "b":
                    event = await server.emit_button_pressed()
                    print(f"Sent button pressed: {event['id']}")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, previous)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host", default="127.0.0.1", help="Host to bind the mock bridge"
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Port to bind the mock bridge"
    )
    parser.add_argument(
        "--token",
        default="mock-hue-token",
        help="Hue application key required by mock endpoints",
    )
    return parser.parse_args(argv)


async def run(host: str, port: int, token: str) -> None:
    server = MockHueBridgeServer(host=host, port=port, token=token)
    await server.start()
    print(f"Mock Hue Bridge listening at {server.base_url}")
    print(f"Event stream: {server.base_url}/eventstream/clip/v2")
    print(f"Hue application key: {token}")
    try:
        await run_keyboard_loop(server)
    finally:
        await server.stop()


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    with suppress(KeyboardInterrupt):
        asyncio.run(run(args.host, args.port, args.token))


if __name__ == "__main__":
    main()
