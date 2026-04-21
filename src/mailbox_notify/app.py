"""Application entry point and web server."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
from pathlib import Path
from typing import Protocol

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from .config import (
    CONFIG_PATH,
    Config,
    ensure_config_file,
    is_config_complete,
    load_config,
    save_config,
)
from .hue import (
    AioHueClient,
    HueClient,
    HueDiscoveryError,
    HueTokenCreationError,
    button_pressed,
    create_hue_application_key,
    discover_hue_buttons,
    discover_hue_bridges,
    discover_hue_contacts,
    mail_detected,
)
from .pixoo import PixooDisplay, create_pixoo_display, discover_pixoo_devices
from .runtime_state import (
    STATE_PATH,
    ensure_runtime_state_file,
    save_runtime_state,
    updated_runtime_state,
)
from .state import HueEventType, MailboxStateMachine


LOGGER = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).with_name("static")
INDEX_HTML_PATH = STATIC_DIR / "index.html"


class RuntimeManager(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def restart(self, config: Config | None = None) -> None: ...

    async def trigger_contact_test(self) -> None: ...

    async def trigger_button_test(self) -> None: ...

    def status(self) -> dict[str, bool]: ...


class ConfigPayload(BaseModel):
    hue_base_url: str = ""
    hue_api_token: str = ""
    hue_contact_id: str = ""
    hue_button_id: str = ""
    pixoo_host: str = ""

    def to_config(self) -> Config:
        data = {key: value.strip() for key, value in self.model_dump().items()}
        return Config(**data)


class HueBridgePayload(BaseModel):
    id: str
    internalipaddress: str
    base_url: str


class HueResourceDiscoveryPayload(BaseModel):
    hue_base_url: str = ""
    hue_api_token: str = ""


class HueContactPayload(BaseModel):
    id: str
    name: str
    owner_rid: str


class HueButtonPayload(BaseModel):
    id: str
    name: str
    owner_rid: str
    control_id: str


class PixooDevicePayload(BaseModel):
    name: str
    host: str
    device_id: str
    device_mac: str
    hardware: str


class CreateHueTokenPayload(BaseModel):
    hue_base_url: str = ""


class HueTokenResponse(BaseModel):
    token: str
    clientkey: str = ""


class MailboxRuntimeError(RuntimeError):
    """Raised when the mailbox runtime cannot handle a requested action."""


class MailboxRuntime:
    def __init__(
        self, config: Config, display: PixooDisplay, state_path: Path = STATE_PATH
    ) -> None:
        self.config = config
        self.display = display
        self._state_path = state_path
        persisted_state = ensure_runtime_state_file(state_path)
        self.state_machine = MailboxStateMachine(
            mail_present=persisted_state.mail_present
        )
        self._event_lock = asyncio.Lock()

    async def run(self) -> None:
        await self.sync_display_from_state()
        while True:
            hue_client = AioHueClient(
                base_url=self.config.hue_base_url,
                api_token=self.config.hue_api_token,
                contact_id=self.config.hue_contact_id,
                button_id=self.config.hue_button_id,
            )
            try:
                await serve(
                    hue_client, self.display, self.state_machine, self.handle_event
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("Hue stream failed, reconnecting")
                await asyncio.sleep(5)

    async def sync_display_from_state(self) -> None:
        async with self._event_lock:
            if self.state_machine.mail_present:
                await self.display.show_new_mail()
            else:
                await self.display.clear()

    async def handle_event(self, event) -> None:
        async with self._event_lock:
            LOGGER.info("Received Hue event: %s", event.kind.name)
            await self.state_machine.handle(event, self.display)
            if event.kind in {HueEventType.MAIL_DETECTED, HueEventType.BUTTON_PRESSED}:
                save_runtime_state(
                    updated_runtime_state(self.state_machine.mail_present),
                    self._state_path,
                )

    async def trigger_contact_test(self) -> None:
        await self.handle_event(mail_detected())

    async def trigger_button_test(self) -> None:
        await self.handle_event(button_pressed())


class MailboxRuntimeManager:
    def __init__(self, config_path: Path, state_path: Path = STATE_PATH) -> None:
        self._config_path = config_path
        self._state_path = state_path
        self._task: asyncio.Task[None] | None = None
        self._runtime: MailboxRuntime | None = None
        self._lock = asyncio.Lock()
        self._config = ensure_config_file(config_path)
        ensure_runtime_state_file(state_path)

    async def start(self) -> None:
        async with self._lock:
            self._config = load_config(self._config_path)
            await self._start_locked(self._config)

    async def stop(self) -> None:
        async with self._lock:
            await self._stop_locked()

    async def restart(self, config: Config | None = None) -> None:
        async with self._lock:
            self._config = load_config(self._config_path) if config is None else config
            await self._stop_locked()
            await self._start_locked(self._config)

    async def trigger_contact_test(self) -> None:
        async with self._lock:
            if not self._config.hue_contact_id:
                raise MailboxRuntimeError("Hue Contact ID is required before testing.")
            runtime = self._runtime
        if runtime is None:
            raise MailboxRuntimeError(
                "Runtime is not active. Save a complete configuration first."
            )
        await runtime.trigger_contact_test()

    async def trigger_button_test(self) -> None:
        async with self._lock:
            if not self._config.hue_button_id:
                raise MailboxRuntimeError("Hue Button ID is required before testing.")
            runtime = self._runtime
        if runtime is None:
            raise MailboxRuntimeError(
                "Runtime is not active. Save a complete configuration first."
            )
        await runtime.trigger_button_test()

    def status(self) -> dict[str, bool]:
        return {
            "configured": is_config_complete(self._config),
            "running": self._task is not None and not self._task.done(),
        }

    async def _start_locked(self, config: Config) -> None:
        if not is_config_complete(config):
            LOGGER.info(
                "Mailbox runtime not started because configuration is incomplete"
            )
            self._task = None
            self._runtime = None
            return
        if self._task is not None and not self._task.done():
            return
        display = await create_pixoo_display(config.pixoo_host)
        self._runtime = MailboxRuntime(config, display, self._state_path)
        self._task = asyncio.create_task(self._runtime.run())

    async def _stop_locked(self) -> None:
        if self._task is None:
            self._runtime = None
            return
        task = self._task
        self._task = None
        self._runtime = None
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def serve(
    hue_client: HueClient,
    display: PixooDisplay,
    state_machine: MailboxStateMachine,
    event_handler=None,
) -> None:
    await hue_client.connect()
    try:
        async for event in hue_client.events():
            if event_handler is not None:
                await event_handler(event)
            else:
                LOGGER.info("Received Hue event: %s", event.kind.name)
                await state_machine.handle(event, display)
    finally:
        await hue_client.disconnect()


async def run_mailbox_runtime(config: Config) -> None:
    display = await create_pixoo_display(config.pixoo_host)
    runtime = MailboxRuntime(config, display)
    await runtime.run()


def create_app(config_path: Path = CONFIG_PATH) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ensure_config_file(config_path)
        ensure_runtime_state_file(STATE_PATH)
        app.state.runtime_manager = MailboxRuntimeManager(config_path, STATE_PATH)
        await app.state.runtime_manager.start()
        try:
            yield
        finally:
            await app.state.runtime_manager.stop()

    app = FastAPI(lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(INDEX_HTML_PATH)

    @app.get("/api/config")
    async def get_config() -> ConfigPayload:
        return ConfigPayload(**load_config(config_path).__dict__)

    @app.put("/api/config")
    async def put_config(payload: ConfigPayload) -> dict[str, object]:
        config = payload.to_config()
        save_config(config, config_path)
        await app.state.runtime_manager.restart(config)
        return {"config": payload.model_dump(), **app.state.runtime_manager.status()}

    @app.get("/api/discover/hue-bridges")
    async def get_hue_bridges() -> list[HueBridgePayload]:
        bridges = await discover_hue_bridges()
        return [HueBridgePayload(**bridge) for bridge in bridges]

    @app.get("/api/discover/pixoo")
    async def get_pixoo_devices() -> list[PixooDevicePayload]:
        devices = await discover_pixoo_devices()
        return [PixooDevicePayload(**device) for device in devices]

    @app.post("/api/discover/hue-contacts")
    async def post_hue_contacts(
        payload: HueResourceDiscoveryPayload,
    ) -> list[HueContactPayload]:
        try:
            contacts = await discover_hue_contacts(
                payload.hue_base_url.strip(),
                payload.hue_api_token.strip(),
            )
        except HueDiscoveryError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return [HueContactPayload(**contact) for contact in contacts]

    @app.post("/api/discover/hue-buttons")
    async def post_hue_buttons(
        payload: HueResourceDiscoveryPayload,
    ) -> list[HueButtonPayload]:
        try:
            buttons = await discover_hue_buttons(
                payload.hue_base_url.strip(),
                payload.hue_api_token.strip(),
            )
        except HueDiscoveryError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return [HueButtonPayload(**button) for button in buttons]

    @app.post("/api/test/hue-contact")
    async def post_test_hue_contact() -> dict[str, bool]:
        try:
            await app.state.runtime_manager.trigger_contact_test()
        except MailboxRuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True}

    @app.post("/api/test/hue-button")
    async def post_test_hue_button() -> dict[str, bool]:
        try:
            await app.state.runtime_manager.trigger_button_test()
        except MailboxRuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True}

    @app.post("/api/hue/create-token")
    async def post_hue_create_token(
        payload: CreateHueTokenPayload,
    ) -> HueTokenResponse:
        try:
            created = await create_hue_application_key(payload.hue_base_url.strip())
        except HueTokenCreationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return HueTokenResponse(**created)

    return app


app = create_app()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
