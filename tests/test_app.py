from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from mailbox_notify.app import (
    MailboxRuntime,
    MailboxRuntimeError,
    create_app,
    main,
    run_mailbox_runtime,
    serve,
)
from mailbox_notify.config import Config, default_config, load_config
from mailbox_notify.hue import HueTokenCreationError, button_pressed, mail_detected
from mailbox_notify.runtime_state import (
    RuntimeState,
    load_runtime_state,
    save_runtime_state,
)
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


class FakePixooDisplay:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def show_new_mail(self) -> None:
        self.calls.append("show_new_mail")

    async def clear(self) -> None:
        self.calls.append("clear")


class FakeRuntimeManager:
    last_instance: FakeRuntimeManager | None = None

    def __init__(self, config_path: Path, state_path: Path | None = None) -> None:
        self.config_path = config_path
        self.state_path = state_path
        self.started = False
        self.stopped = False
        self.restarted_with: Config | None = None
        self._status = {"configured": False, "running": False}
        FakeRuntimeManager.last_instance = self

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def restart(self, config: Config | None = None) -> None:
        self.restarted_with = config
        self._status = {
            "configured": config is not None and bool(config.hue_base_url),
            "running": config is not None and bool(config.hue_base_url),
        }

    async def trigger_contact_test(self) -> None:
        return None

    async def trigger_button_test(self) -> None:
        return None

    def status(self) -> dict[str, bool]:
        return self._status


class AppServeTests(unittest.IsolatedAsyncioTestCase):
    async def test_serve_drives_display_from_hue_events(self) -> None:
        hue = FakeHueClient([mail_detected(), button_pressed()])
        display = FakePixooDisplay()
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


class AppRuntimeTests(unittest.TestCase):
    def test_run_mailbox_runtime_builds_hue_client_from_config(self) -> None:
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

        fake_display = FakePixooDisplay()

        with (
            patch(
                "mailbox_notify.app.create_pixoo_display",
                new=AsyncMock(return_value=fake_display),
            ),
            patch("mailbox_notify.app.serve", side_effect=assert_client),
        ):
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(run_mailbox_runtime(fake_config))

    def test_main_runs_uvicorn(self) -> None:
        with patch("mailbox_notify.app.uvicorn.run") as run_mock:
            main()

        run_mock.assert_called_once()


class MailboxRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_display_from_state_shows_mail_when_persisted(self) -> None:
        with TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            save_runtime_state(
                RuntimeState(mail_present=True, last_updated="2026-04-20T12:34:56Z"),
                state_path,
            )
            display = FakePixooDisplay()
            runtime = MailboxRuntime(
                Config(
                    hue_base_url="http://127.0.0.1:8000",
                    hue_api_token="token",
                    hue_contact_id="contact-id",
                    hue_button_id="button-id",
                    pixoo_host="",
                ),
                display,
                state_path,
            )

            await runtime.sync_display_from_state()

            self.assertEqual(display.calls, ["show_new_mail"])

    async def test_sync_display_from_state_clears_when_persisted_false(self) -> None:
        with TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            save_runtime_state(
                RuntimeState(mail_present=False, last_updated="2026-04-20T12:34:56Z"),
                state_path,
            )
            display = FakePixooDisplay()
            runtime = MailboxRuntime(
                Config(
                    hue_base_url="http://127.0.0.1:8000",
                    hue_api_token="token",
                    hue_contact_id="contact-id",
                    hue_button_id="button-id",
                    pixoo_host="",
                ),
                display,
                state_path,
            )

            await runtime.sync_display_from_state()

            self.assertEqual(display.calls, ["clear"])

    async def test_sync_display_from_state_creates_missing_file_and_clears(
        self,
    ) -> None:
        with TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            display = FakePixooDisplay()
            runtime = MailboxRuntime(
                Config(
                    hue_base_url="http://127.0.0.1:8000",
                    hue_api_token="token",
                    hue_contact_id="contact-id",
                    hue_button_id="button-id",
                    pixoo_host="",
                ),
                display,
                state_path,
            )

            await runtime.sync_display_from_state()

            self.assertTrue(state_path.exists())
            self.assertEqual(display.calls, ["clear"])

    async def test_trigger_contact_test_drives_display(self) -> None:
        with TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            runtime = MailboxRuntime(
                Config(
                    hue_base_url="http://127.0.0.1:8000",
                    hue_api_token="token",
                    hue_contact_id="contact-id",
                    hue_button_id="button-id",
                    pixoo_host="",
                ),
                FakePixooDisplay(),
                state_path,
            )

            await runtime.trigger_contact_test()

            self.assertEqual(runtime.display.calls, ["show_new_mail"])

    async def test_trigger_button_test_drives_display(self) -> None:
        with TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            display = FakePixooDisplay()
            runtime = MailboxRuntime(
                Config(
                    hue_base_url="http://127.0.0.1:8000",
                    hue_api_token="token",
                    hue_contact_id="contact-id",
                    hue_button_id="button-id",
                    pixoo_host="",
                ),
                display,
                state_path,
            )

            await runtime.trigger_contact_test()
            await runtime.trigger_button_test()

            self.assertEqual(display.calls, ["show_new_mail", "clear"])

    async def test_runtime_loads_persisted_mail_state_and_button_clears_it(
        self,
    ) -> None:
        with TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            save_runtime_state(
                RuntimeState(mail_present=True, last_updated="2026-04-20T12:34:56Z"),
                state_path,
            )
            display = FakePixooDisplay()
            runtime = MailboxRuntime(
                Config(
                    hue_base_url="http://127.0.0.1:8000",
                    hue_api_token="token",
                    hue_contact_id="contact-id",
                    hue_button_id="button-id",
                    pixoo_host="",
                ),
                display,
                state_path,
            )

            await runtime.trigger_button_test()

            self.assertFalse(runtime.state_machine.mail_present)
            self.assertEqual(display.calls, ["clear"])
            persisted = load_runtime_state(state_path)
            self.assertFalse(persisted.mail_present)
            self.assertTrue(persisted.last_updated.endswith("Z"))


class AppApiTests(unittest.TestCase):
    def test_root_returns_dummy_page_and_config_routes_persist_json(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            with patch("mailbox_notify.app.MailboxRuntimeManager", FakeRuntimeManager):
                app = create_app(config_path)
                with TestClient(app) as client:
                    root = client.get("/")
                    css = client.get("/static/index.css")
                    js = client.get("/static/index.js")
                    config_response = client.get("/api/config")
                    payload = {
                        "hue_base_url": "http://127.0.0.1:8000",
                        "hue_api_token": "token",
                        "hue_contact_id": "contact-id",
                        "hue_button_id": "button-id",
                        "pixoo_host": "",
                    }
                    put_response = client.put("/api/config", json=payload)

                manager = FakeRuntimeManager.last_instance

            self.assertEqual(root.status_code, 200)
            self.assertIn("Configure your mailbox display", root.text)
            self.assertIn("Mailbox Notify", root.text)
            self.assertIn("Discover Bridges", root.text)
            self.assertIn("Discover Pixoo", root.text)
            self.assertIn("Save Settings", root.text)
            self.assertIn("Create Token", root.text)
            self.assertIn('type="text"', root.text)
            self.assertIn("/static/index.css", root.text)
            self.assertIn("/static/index.js", root.text)
            self.assertIn("Discover Contacts", root.text)
            self.assertIn("Discover Buttons", root.text)
            self.assertGreaterEqual(root.text.count(">Test<"), 2)
            self.assertNotIn("What this mock demonstrates", root.text)
            self.assertNotIn("Planned discovery flow", root.text)
            self.assertEqual(css.status_code, 200)
            self.assertIn(".button-primary", css.text)
            self.assertEqual(js.status_code, 200)
            self.assertIn("loadConfig", js.text)
            self.assertIn("/api/config", js.text)
            self.assertIn("/api/hue/create-token", js.text)
            self.assertIn("/api/discover/pixoo", js.text)
            self.assertIn("/api/discover/hue-contacts", js.text)
            self.assertIn("/api/discover/hue-buttons", js.text)
            self.assertIn("/api/test/hue-contact", js.text)
            self.assertIn("/api/test/hue-button", js.text)
            self.assertEqual(config_response.status_code, 200)
            self.assertEqual(config_response.json(), default_config().__dict__)
            self.assertEqual(put_response.status_code, 200)
            self.assertEqual(load_config(config_path), Config(**payload))
            self.assertIsNotNone(manager)
            self.assertTrue(manager.started)
            self.assertTrue(manager.stopped)
            self.assertEqual(manager.restarted_with, Config(**payload))

    def test_hue_bridge_discovery_endpoint_returns_normalized_bridges(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            with (
                patch("mailbox_notify.app.MailboxRuntimeManager", FakeRuntimeManager),
                patch(
                    "mailbox_notify.app.discover_hue_bridges",
                    new=AsyncMock(
                        return_value=[
                            {
                                "id": "bridge-id-1",
                                "internalipaddress": "10.0.0.20",
                                "base_url": "https://10.0.0.20",
                            }
                        ]
                    ),
                ),
            ):
                app = create_app(config_path)
                with TestClient(app) as client:
                    response = client.get("/api/discover/hue-bridges")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json(),
                [
                    {
                        "id": "bridge-id-1",
                        "internalipaddress": "10.0.0.20",
                        "base_url": "https://10.0.0.20",
                    }
                ],
            )

    def test_pixoo_discovery_endpoint_returns_normalized_devices(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            with (
                patch("mailbox_notify.app.MailboxRuntimeManager", FakeRuntimeManager),
                patch(
                    "mailbox_notify.app.discover_pixoo_devices",
                    new=AsyncMock(
                        return_value=[
                            {
                                "name": "Pixoo64",
                                "host": "10.0.0.47",
                                "device_id": "300247395",
                                "device_mac": "2cbcbb116a0c",
                                "hardware": "92",
                            }
                        ]
                    ),
                ),
            ):
                app = create_app(config_path)
                with TestClient(app) as client:
                    response = client.get("/api/discover/pixoo")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json(),
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

    def test_hue_contact_discovery_endpoint_returns_normalized_contacts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            with (
                patch("mailbox_notify.app.MailboxRuntimeManager", FakeRuntimeManager),
                patch(
                    "mailbox_notify.app.discover_hue_contacts",
                    new=AsyncMock(
                        return_value=[
                            {
                                "id": "contact-id-1",
                                "name": "Mailbox Sensor",
                                "owner_rid": "device-id-1",
                            }
                        ]
                    ),
                ),
            ):
                app = create_app(config_path)
                with TestClient(app) as client:
                    response = client.post(
                        "/api/discover/hue-contacts",
                        json={
                            "hue_base_url": "https://10.0.0.20",
                            "hue_api_token": "token",
                        },
                    )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json(),
                [
                    {
                        "id": "contact-id-1",
                        "name": "Mailbox Sensor",
                        "owner_rid": "device-id-1",
                    }
                ],
            )

    def test_hue_button_discovery_endpoint_returns_normalized_buttons(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            with (
                patch("mailbox_notify.app.MailboxRuntimeManager", FakeRuntimeManager),
                patch(
                    "mailbox_notify.app.discover_hue_buttons",
                    new=AsyncMock(
                        return_value=[
                            {
                                "id": "button-id-1",
                                "name": "Mailbox Clear Button",
                                "owner_rid": "device-id-1",
                                "control_id": "1",
                            }
                        ]
                    ),
                ),
            ):
                app = create_app(config_path)
                with TestClient(app) as client:
                    response = client.post(
                        "/api/discover/hue-buttons",
                        json={
                            "hue_base_url": "https://10.0.0.20",
                            "hue_api_token": "token",
                        },
                    )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json(),
                [
                    {
                        "id": "button-id-1",
                        "name": "Mailbox Clear Button",
                        "owner_rid": "device-id-1",
                        "control_id": "1",
                    }
                ],
            )

    def test_hue_create_token_endpoint_returns_token(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            with (
                patch("mailbox_notify.app.MailboxRuntimeManager", FakeRuntimeManager),
                patch(
                    "mailbox_notify.app.create_hue_application_key",
                    new=AsyncMock(
                        return_value={"token": "token-123", "clientkey": "client-456"}
                    ),
                ),
            ):
                app = create_app(config_path)
                with TestClient(app) as client:
                    response = client.post(
                        "/api/hue/create-token",
                        json={"hue_base_url": "https://10.0.0.20"},
                    )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json(), {"token": "token-123", "clientkey": "client-456"}
            )

    def test_hue_create_token_endpoint_returns_bridge_error(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            with (
                patch("mailbox_notify.app.MailboxRuntimeManager", FakeRuntimeManager),
                patch(
                    "mailbox_notify.app.create_hue_application_key",
                    new=AsyncMock(
                        side_effect=HueTokenCreationError("link button not pressed")
                    ),
                ),
            ):
                app = create_app(config_path)
                with TestClient(app) as client:
                    response = client.post(
                        "/api/hue/create-token",
                        json={"hue_base_url": "https://10.0.0.20"},
                    )

            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json(), {"detail": "link button not pressed"})

    def test_hue_contact_test_endpoint_triggers_runtime(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            manager = FakeRuntimeManager(config_path)
            with patch(
                "mailbox_notify.app.MailboxRuntimeManager", return_value=manager
            ):
                app = create_app(config_path)
                with TestClient(app) as client:
                    response = client.post("/api/test/hue-contact")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})

    def test_hue_button_test_endpoint_returns_runtime_error(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            manager = FakeRuntimeManager(config_path)

            async def fail() -> None:
                raise MailboxRuntimeError("Hue Button ID is required before testing.")

            manager.trigger_button_test = fail
            with patch(
                "mailbox_notify.app.MailboxRuntimeManager", return_value=manager
            ):
                app = create_app(config_path)
                with TestClient(app) as client:
                    response = client.post("/api/test/hue-button")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(), {"detail": "Hue Button ID is required before testing."}
        )
