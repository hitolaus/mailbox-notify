"""Philips Hue v2 event stream adapter."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
import logging
from typing import Protocol
from urllib.parse import urlparse

import aiohttp
from aiohue.v2 import HueBridgeV2
from aiohue.v2.controllers.events import EventType
from aiohue.v2.models.button import Button, ButtonEvent
from aiohue.v2.models.contact import Contact, ContactState

from .state import HueEvent, HueEventType


LOGGER = logging.getLogger(__name__)
HUE_DISCOVERY_URL = "https://discovery.meethue.com/"


class HueClient(Protocol):
    async def connect(self) -> None: ...

    async def disconnect(self) -> None: ...

    def events(self) -> AsyncIterator[HueEvent]: ...


async def discover_hue_bridges() -> list[dict[str, str]]:
    async with aiohttp.ClientSession() as session:
        async with session.get(HUE_DISCOVERY_URL) as response:
            response.raise_for_status()
            payload = await response.json()

    bridges: list[dict[str, str]] = []
    for entry in payload:
        bridge_id = str(entry.get("id", "")).strip()
        ip_address = str(entry.get("internalipaddress", "")).strip()
        if not bridge_id or not ip_address:
            continue
        bridges.append(
            {
                "id": bridge_id,
                "internalipaddress": ip_address,
                "base_url": f"https://{ip_address}",
            }
        )

    return bridges


class ConfigurableHueBridge(HueBridgeV2):
    """Hue bridge client with a configurable base URL."""

    def __init__(self, base_url: str, app_key: str) -> None:
        parsed = urlparse(base_url)
        host = parsed.netloc or parsed.path
        super().__init__(host=host, app_key=app_key)
        self._base_url = base_url.rstrip("/")

    @asynccontextmanager
    async def create_request(self, method: str, path: str, **kwargs):
        if self._websession is None:
            connector = aiohttp.TCPConnector(limit_per_host=3)
            self._websession = aiohttp.ClientSession(connector=connector)

        url = f"{self._base_url}/{path}"
        headers = kwargs.setdefault("headers", {})
        headers["hue-application-key"] = self._app_key
        kwargs["ssl"] = False

        async with self._websession.request(method, url, **kwargs) as response:
            yield response


@dataclass
class AioHueClient(HueClient):
    """Map aiohue contact and button updates to app events."""

    base_url: str
    api_token: str
    contact_id: str
    button_id: str

    def __post_init__(self) -> None:
        self._bridge: ConfigurableHueBridge | None = None
        self._events: asyncio.Queue[HueEvent | None] = asyncio.Queue()
        self._unsubscribe_contact = None
        self._unsubscribe_button = None
        self._connected = False

    async def connect(self) -> None:
        if self._connected:
            return

        self._bridge = ConfigurableHueBridge(self.base_url, self.api_token)
        await self._bridge.initialize()
        await self._wait_until_eventstream_connected()
        self._unsubscribe_contact = self._bridge.sensors.contact.subscribe(
            self._handle_contact_update,
            id_filter=self.contact_id,
            event_filter=EventType.RESOURCE_UPDATED,
        )
        self._unsubscribe_button = self._bridge.sensors.button.subscribe(
            self._handle_button_update,
            id_filter=self.button_id,
            event_filter=EventType.RESOURCE_UPDATED,
        )
        self._connected = True
        LOGGER.info("Connected to Hue bridge at %s", self.base_url)

    async def disconnect(self) -> None:
        if not self._connected:
            return

        if self._unsubscribe_contact is not None:
            self._unsubscribe_contact()
            self._unsubscribe_contact = None
        if self._unsubscribe_button is not None:
            self._unsubscribe_button()
            self._unsubscribe_button = None
        if self._bridge is not None:
            await self._bridge.close()
            self._bridge = None
        self._connected = False
        await self._events.put(None)

    async def events(self) -> AsyncIterator[HueEvent]:
        while True:
            event = await self._events.get()
            if event is None:
                return
            yield event

    def _handle_contact_update(self, event_type: EventType, contact: Contact) -> None:
        if event_type is not EventType.RESOURCE_UPDATED:
            return
        report = contact.contact_report
        if report is None or report.state is not ContactState.CONTACT:
            return
        self._events.put_nowait(mail_detected())

    def _handle_button_update(self, event_type: EventType, button: Button) -> None:
        if event_type is not EventType.RESOURCE_UPDATED:
            return
        feature = button.button
        report = None if feature is None else feature.button_report
        if report is None or report.event is not ButtonEvent.INITIAL_PRESS:
            return
        self._events.put_nowait(button_pressed())

    async def _wait_until_eventstream_connected(self) -> None:
        assert self._bridge is not None
        for _ in range(50):
            if self._bridge.events.connected:
                return
            await asyncio.sleep(0.1)
        raise TimeoutError(
            f"Timed out connecting to Hue event stream at {self.base_url}"
        )


def mail_detected() -> HueEvent:
    return HueEvent(HueEventType.MAIL_DETECTED)


def button_pressed() -> HueEvent:
    return HueEvent(HueEventType.BUTTON_PRESSED)
