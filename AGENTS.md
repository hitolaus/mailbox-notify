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
- `config.py`: JSON file based configuration loading and persistence.
- `app.py`: FastAPI app, configuration API, and runtime manager.
- `src/cli/mock_hue_bridge.py`: interactive local mock Hue Bridge with HTTP event stream and resource endpoints.

## Integration details

- Use `aiohue` for Hue bridge communication.
- The Hue adapter currently uses explicit `HUE_CONTACT_ID` and `HUE_BUTTON_ID` resource IDs instead of auto-discovery.
- The Hue adapter supports both real bridges and the local mock bridge via `hue_base_url` in the JSON config.
- The FastAPI app can discover Hue Bridges on the LAN through the Hue discovery service for configuration UI use.
- The config UI can create Hue application keys through the bridge link-button flow.
- The config UI can discover Hue contacts and buttons from the configured bridge.
- The Pixoo adapter uses the `pixoo` library for device control.
- Pixoo device selection prefers `pixoo_host`; otherwise it auto-discovers on the LAN and uses the first device returned.
- If Pixoo auto-discovery is not available through the library, fall back to `https://app.divoom-gz.com/Device/ReturnSameLANDevice`.
- Treat the mailbox sensor as the source of truth for the "new mail" state.
- Treat the Hue button press as the only clear action.
- Treat Hue `contact_report.state == contact` as the mail-detected signal.
- Treat Hue `button.button_report.event == initial_press` as the clear signal.
- The Pixoo notification rendering is a continuously looping modern envelope-opening animation.

## Code style

- Keep changes minimal and focused.
- Prefer small functions over deep abstraction.
- Add tests for state transitions and event handling before expanding features.
- Avoid premature support for extra sensors, buttons, or displays.

## Operational expectations

- The app is intended to run locally on the LAN.
- Do not assume cloud connectivity.
- Log enough detail to debug bridge connection issues and event handling.
- The app logs each normalized Hue event when it is received in `app.py`.
- The main application process is a FastAPI server that hosts a simple configuration page and JSON API.
- Configuration is stored in a local `config.json` file in the project root and updates should restart the runtime immediately.
- The current UI loads and saves real config values, has live Hue bridge and Pixoo discovery controls, supports Hue token creation, and discovers real contacts/buttons from the configured bridge.
- The mock bridge is HTTP-only and is intended for local development and Pixoo integration testing.
