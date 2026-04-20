"""Application entry point."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from .config import load_config
from .hue import AioHueClient, HueClient
from .pixoo import PixooDisplay, StubPixooDisplay
from .state import MailboxStateMachine


LOGGER = logging.getLogger(__name__)


async def serve(
    hue_client: HueClient,
    display: PixooDisplay,
    state_machine: MailboxStateMachine,
) -> None:
    await hue_client.connect()
    try:
        async for event in hue_client.events():
            LOGGER.info("Received Hue event: %s", event.kind.name)
            await state_machine.handle(event, display)
    finally:
        await hue_client.disconnect()


async def run() -> None:
    config = load_config()
    display = StubPixooDisplay()
    state_machine = MailboxStateMachine()

    while True:
        hue_client = AioHueClient(
            base_url=config.hue_base_url,
            api_token=config.hue_api_token,
            contact_id=config.hue_contact_id,
            button_id=config.hue_button_id,
        )
        try:
            await serve(hue_client, display, state_machine)
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("Hue stream failed, reconnecting")
            await asyncio.sleep(5)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    with suppress(KeyboardInterrupt):
        asyncio.run(run())


if __name__ == "__main__":
    main()
