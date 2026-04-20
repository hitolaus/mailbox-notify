"""Pixoo64 display adapter."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import sys
from types import ModuleType
from typing import Any, Protocol

import aiohttp


LOGGER = logging.getLogger(__name__)
DISCOVERY_URL = "https://app.divoom-gz.com/Device/ReturnSameLANDevice"
BACKGROUND = (8, 12, 24)
SHADOW = (18, 28, 48)
ENVELOPE = (238, 243, 255)
ENVELOPE_DIM = (190, 204, 232)
ACCENT = (74, 163, 255)
ACCENT_DIM = (46, 113, 196)
ENVELOPE_LEFT = 16
ENVELOPE_TOP = 24
ENVELOPE_RIGHT = 47
ENVELOPE_BOTTOM = 41
LETTER_LEFT = 20
LETTER_RIGHT = 43
LETTER_TOP_CLOSED = 27
LETTER_BOTTOM = 37
CENTER_X = (ENVELOPE_LEFT + ENVELOPE_RIGHT) // 2
LABEL_X = 18
LABEL_Y = 50
FRAMES = (
    {"open": 0.0, "letter_offset": 0, "hold": 5.0},
    {"open": 0.16, "letter_offset": 0, "hold": 0.08},
    {"open": 0.32, "letter_offset": 0, "hold": 0.08},
    {"open": 0.54, "letter_offset": 1, "hold": 0.08},
    {"open": 0.76, "letter_offset": 3, "hold": 0.08},
    {"open": 1.0, "letter_offset": 5, "hold": 0.10},
    {"open": 1.0, "letter_offset": 7, "hold": 0.28},
    {"open": 0.76, "letter_offset": 3, "hold": 0.08},
    {"open": 0.54, "letter_offset": 1, "hold": 0.08},
    {"open": 0.32, "letter_offset": 0, "hold": 0.08},
    {"open": 0.16, "letter_offset": 0, "hold": 0.08},
)


class PixooDisplay(Protocol):
    async def show_new_mail(self) -> None: ...

    async def clear(self) -> None: ...


@dataclass
class PixooClient(PixooDisplay):
    """Minimal async adapter over the pixoo library."""

    _device: Any
    host: str

    def __post_init__(self) -> None:
        self._animation_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    async def show_new_mail(self) -> None:
        if self._animation_task is not None and not self._animation_task.done():
            return
        self._animation_task = asyncio.create_task(self._run_mail_animation())

    async def clear(self) -> None:
        task = self._animation_task
        self._animation_task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        async with self._lock:
            await asyncio.to_thread(self._clear_sync)

    async def _run_mail_animation(self) -> None:
        try:
            while True:
                for frame in FRAMES:
                    async with self._lock:
                        await asyncio.to_thread(
                            self._render_envelope_frame_sync,
                            frame["open"],
                            frame["letter_offset"],
                        )
                    await asyncio.sleep(frame["hold"])
        except asyncio.CancelledError:
            raise

    def _render_envelope_frame_sync(
        self, open_amount: float, letter_offset: int
    ) -> None:
        self._device.fill(BACKGROUND)
        self._draw_shadow()
        self._draw_letter(letter_offset)
        self._draw_envelope_shell()
        self._draw_flap(open_amount)
        self._draw_label()
        self._device.push()

    def _draw_shadow(self) -> None:
        self._device.draw_filled_rectangle(
            (ENVELOPE_LEFT + 4, ENVELOPE_BOTTOM + 4),
            (ENVELOPE_RIGHT - 4, ENVELOPE_BOTTOM + 6),
            SHADOW,
        )

    def _draw_letter(self, letter_offset: int) -> None:
        top = LETTER_TOP_CLOSED - letter_offset
        self._device.draw_filled_rectangle(
            (LETTER_LEFT, top),
            (LETTER_RIGHT, LETTER_BOTTOM - letter_offset),
            ENVELOPE,
        )
        self._device.draw_filled_rectangle(
            (LETTER_LEFT + 2, top + 2),
            (LETTER_RIGHT - 2, top + 4),
            ACCENT,
        )
        self._device.draw_line(
            (LETTER_LEFT + 3, top + 8),
            (LETTER_RIGHT - 3, top + 8),
            ENVELOPE_DIM,
        )
        self._device.draw_line(
            (LETTER_LEFT + 3, top + 11),
            (LETTER_RIGHT - 6, top + 11),
            ENVELOPE_DIM,
        )

    def _draw_envelope_shell(self) -> None:
        self._device.draw_filled_rectangle(
            (ENVELOPE_LEFT, ENVELOPE_TOP),
            (ENVELOPE_RIGHT, ENVELOPE_BOTTOM),
            ENVELOPE_DIM,
        )
        self._device.draw_filled_rectangle(
            (ENVELOPE_LEFT + 1, ENVELOPE_TOP + 1),
            (ENVELOPE_RIGHT - 1, ENVELOPE_BOTTOM - 1),
            ENVELOPE,
        )
        self._device.draw_line(
            (ENVELOPE_LEFT, ENVELOPE_BOTTOM),
            (CENTER_X, ENVELOPE_TOP + 8),
            ENVELOPE_DIM,
        )
        self._device.draw_line(
            (ENVELOPE_RIGHT, ENVELOPE_BOTTOM),
            (CENTER_X, ENVELOPE_TOP + 8),
            ENVELOPE_DIM,
        )
        self._device.draw_line(
            (ENVELOPE_LEFT + 1, ENVELOPE_BOTTOM - 1),
            (CENTER_X, ENVELOPE_TOP + 10),
            ACCENT_DIM,
        )
        self._device.draw_line(
            (ENVELOPE_RIGHT - 1, ENVELOPE_BOTTOM - 1),
            (CENTER_X, ENVELOPE_TOP + 10),
            ACCENT_DIM,
        )

    def _draw_flap(self, open_amount: float) -> None:
        peak_y = ENVELOPE_TOP + 8 - round(open_amount * 13)
        shoulder_y = ENVELOPE_TOP + 8 - round(open_amount * 6)
        left_mid_x = ENVELOPE_LEFT + 8
        right_mid_x = ENVELOPE_RIGHT - 8

        self._device.draw_line(
            (ENVELOPE_LEFT, ENVELOPE_TOP), (left_mid_x, shoulder_y), ENVELOPE_DIM
        )
        self._device.draw_line(
            (left_mid_x, shoulder_y), (CENTER_X, peak_y), ENVELOPE_DIM
        )
        self._device.draw_line(
            (CENTER_X, peak_y), (right_mid_x, shoulder_y), ENVELOPE_DIM
        )
        self._device.draw_line(
            (right_mid_x, shoulder_y), (ENVELOPE_RIGHT, ENVELOPE_TOP), ENVELOPE_DIM
        )

        inner_left_x = ENVELOPE_LEFT + 2
        inner_right_x = ENVELOPE_RIGHT - 2
        inner_left_mid = left_mid_x + 1
        inner_right_mid = right_mid_x - 1
        inner_shoulder_y = shoulder_y + 1
        inner_peak_y = peak_y + 1
        self._device.draw_line(
            (inner_left_x, ENVELOPE_TOP + 1), (inner_left_mid, inner_shoulder_y), ACCENT
        )
        self._device.draw_line(
            (inner_left_mid, inner_shoulder_y), (CENTER_X, inner_peak_y), ACCENT
        )
        self._device.draw_line(
            (CENTER_X, inner_peak_y), (inner_right_mid, inner_shoulder_y), ACCENT
        )
        self._device.draw_line(
            (inner_right_mid, inner_shoulder_y),
            (inner_right_x, ENVELOPE_TOP + 1),
            ACCENT,
        )

    def _draw_label(self) -> None:
        self._device.draw_text("New Mail", (LABEL_X, LABEL_Y), ENVELOPE)

    def _clear_sync(self) -> None:
        self._device.clear()
        self._device.push()


async def create_pixoo_display(host: str) -> PixooClient:
    if host:
        device = await asyncio.to_thread(_build_pixoo_device, host)
        LOGGER.info("Using Pixoo device at %s from PIXOO_HOST", host)
        return PixooClient(device, host)

    try:
        device = await asyncio.to_thread(_build_pixoo_device, None)
        discovered_host = getattr(device, "ip_address", None)
        if not discovered_host:
            raise RuntimeError("Pixoo library did not return a device IP")
        LOGGER.info(
            "Auto-discovered Pixoo device at %s via pixoo library", discovered_host
        )
        return PixooClient(device, discovered_host)
    except Exception as exc:
        LOGGER.warning(
            "Pixoo library auto-discovery failed, falling back to Divoom LAN API: %s",
            exc,
        )

    discovered_host = await _discover_lan_pixoo_host()
    device = await asyncio.to_thread(_build_pixoo_device, discovered_host)
    LOGGER.info(
        "Auto-discovered Pixoo device at %s via Divoom LAN API", discovered_host
    )
    return PixooClient(device, discovered_host)


def _build_pixoo_device(host: str | None):
    pixoo_class = _load_pixoo_class()
    return pixoo_class(host)


def _load_pixoo_class():
    try:
        import tkinter  # noqa: F401
    except ModuleNotFoundError as exc:
        if exc.name != "_tkinter":
            raise
        sys.modules.setdefault("tkinter", ModuleType("tkinter"))

    from pixoo.objects.pixoo import Pixoo

    return Pixoo


async def _discover_lan_pixoo_host() -> str:
    async with aiohttp.ClientSession() as session:
        async with session.post(DISCOVERY_URL) as response:
            response.raise_for_status()
            payload = await response.json()

    if payload.get("ReturnCode") != 0:
        raise RuntimeError(
            f"Divoom LAN discovery failed: {payload.get('ReturnMessage', 'unknown error')}"
        )

    devices = payload.get("DeviceList", [])
    if not devices:
        raise RuntimeError("No Pixoo devices found on the local network")

    return devices[0]["DevicePrivateIP"]
