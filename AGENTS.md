# AGENTS.md

## Project rules

- Use Python for the implementation.
- Prefer async code and event-driven updates.
- Assume exactly one Philips Hue Bridge and one Pixoo64.
- Do not add multi-device abstractions unless they are needed later.
- Keep device adapters small and isolated.

## Architecture guidance

- `hue.py`: Philips Hue v2 event stream client and event mapping.
- `pixoo.py`: Pixoo64 display adapter.
- `state.py`: mailbox notification state machine.
- `runtime_state.py`: persisted mailbox runtime state (`mail_present` and `last_updated`).
- `config.py`: JSON file based configuration loading and persistence.
- `app.py`: FastAPI app, configuration API, and runtime manager.
- `static/`: bundled configuration UI served by the FastAPI app.
- `src/cli/mock_hue_bridge.py`: interactive local mock Hue Bridge with HTTP event stream and resource endpoints.
- `tests/`: unit tests for config, runtime state, app/runtime behavior, Hue integration, Pixoo behavior, and the mock bridge.

## Integration details

- Use `aiohue` for Hue bridge communication.
- The Hue adapter currently uses configured `hue_contact_id` and `hue_button_id` resource IDs instead of auto-discovery at runtime.
- The Hue adapter supports both real bridges and the local mock bridge via `hue_base_url` in the JSON config.
- The Hue client waits for the v2 event stream to report connected before subscribing to contact and button updates.
- The FastAPI app can discover Hue Bridges on the LAN through the Hue discovery service for configuration UI use.
- The config UI can create Hue application keys through the bridge link-button flow.
- The config UI can discover Hue contacts and buttons from the configured bridge.
- The config UI has `Test` buttons for contact/button flows that trigger internal normalized events without contacting the Hue bridge.
- The Pixoo adapter uses the `pixoo` library for device control.
- Pixoo device selection prefers `pixoo_host`; otherwise it first tries the library's discovery path and then falls back to `https://app.divoom-gz.com/Device/ReturnSameLANDevice`.
- The `/api/discover/pixoo` endpoint currently uses the Divoom LAN discovery API directly and returns normalized device metadata.
- Treat the mailbox sensor as the source of truth for the "new mail" state.
- Treat the Hue button press as the only clear action.
- Persist runtime mailbox state in `state.json` with `mail_present` and `last_updated`.
- Restore the Pixoo display from persisted mailbox state when the runtime starts.
- Clear the Pixoo display unconditionally on Hue button presses to avoid drift between persisted state and displayed state.
- Treat Hue `contact_report.state == contact` as the mail-detected signal.
- Treat Hue `button.button_report.event == initial_press` as the clear signal.
- The Pixoo notification rendering is a continuously looping modern envelope-opening animation.

## Code style

- Keep changes minimal and focused.
- Prefer small functions over deep abstraction.
- Add tests for state transitions and event handling before expanding features.
- Ensure `ruff` passes after modifications.
- Avoid premature support for extra sensors, buttons, or displays.

## Operational expectations

- The app is intended to run locally on the LAN.
- Do not assume cloud connectivity.
- Log enough detail to debug bridge connection issues and event handling.
- The app logs each normalized Hue event when it is received in `app.py`.
- The main application process is a FastAPI server that hosts a simple configuration page and JSON API.
- Configuration is stored in a local `config.json` file by default and updates should restart the runtime immediately.
- The runtime state is stored separately in `state.json` by default.
- Both config and runtime state paths can be overridden with `MAILBOX_NOTIFY_CONFIG_PATH` and `MAILBOX_NOTIFY_STATE_PATH`.
- The web server bind host and port can be overridden with `MAILBOX_NOTIFY_HOST` and `MAILBOX_NOTIFY_PORT`.
- The UI does not expose a separate runtime status badge.
- The current UI loads and saves real config values, has live Hue bridge and Pixoo discovery controls, supports Hue token creation, and discovers real contacts/buttons from the configured bridge.
- The mock bridge is HTTP-only and is intended for local development and Pixoo integration testing.
- The runtime only starts when the Hue bridge URL, Hue API token, Hue contact ID, and Hue button ID are configured; `pixoo_host` remains optional because Pixoo can be auto-discovered.
