# mailbox-notify

Local mediator for a Philips Hue mailbox contact sensor and a Divoom Pixoo64 display.

## Goal

- Listen to Philips Hue API v2 event stream updates from one Hue Bridge.
- Detect when the mailbox contact sensor changes state.
- Show a persistent new-mail icon on the Pixoo64.
- Clear the display only when a Philips Hue button is pressed.

## Assumptions

- One Hue Bridge.
- One Pixoo64.
- The app runs locally on the same network as both devices.
- The Hue Bridge is already available on the network, including when hosted as a Docker service.

## Planned stack

- Python 3.11+
- `uv` for dependency management and environment sync.
- `aiohue` for Philips Hue v2 and event-stream handling.
- `pixoo` for Pixoo64 device control.

## Getting Started

- Install `uv` if needed: `brew install uv`
- Sync dependencies: `uv sync --locked`
- Run the mock Hue bridge: `uv run mailbox-notify-mock-hue`
- Run the app: `uv run mailbox-notify`
- Open `http://127.0.0.1:8000/`
- The app creates `config.json` in the project root on first start

## Linux Docker Deployment

- Production deployment is Linux-only via Docker Compose in `compose.yml`.
- This setup uses `network_mode: host` so the app binds directly on the Linux host network.
- Runtime data is stored in `./data/` in the cloned repo.

### Requirements

- Docker Engine with the Compose plugin installed

### Start

- Clone the repo and enter it.
- Start the service: `docker compose up -d --build`
- Open `http://<linux-host-ip>:8000/`
- Persistent files are created in `./data/`:
- `config.json`
- `state.json`

### Update

- Pull the latest changes: `git pull`
- Rebuild and restart: `docker compose up -d --build`

### Stop

- Stop the service: `docker compose down`

### Notes

- The container sets:
- `MAILBOX_NOTIFY_CONFIG_PATH=/data/config.json`
- `MAILBOX_NOTIFY_STATE_PATH=/data/state.json`
- `MAILBOX_NOTIFY_HOST=0.0.0.0`
- `MAILBOX_NOTIFY_PORT=8000`
- Linux host networking is the supported deployment mode.
- For stable long-running operation, save explicit `hue_base_url` and `pixoo_host` values once initial setup is complete.

## Intended structure

- `src/mailbox_notify/` for the application package.
- `src/cli/` for developer-facing helper CLIs such as the mock Hue Bridge.
- `tests/` for state and event handling tests.
- `AGENTS.md` for implementation guidance and project rules.

## Implementation notes

- Keep Hue-specific code isolated from Pixoo-specific code.
- Prefer async I/O throughout.
- Keep the state machine small and explicit: `mail_present` on sensor trigger, `cleared` on button press.
- Make display updates idempotent so repeated sensor events do not cause unnecessary redraws.
- The app now uses a real `aiohue` event-stream client and can point at either a Hue bridge or the local mock bridge.
- The app now uses a real Pixoo adapter built on the `pixoo` library.
- The main process is a FastAPI server with a lightweight configuration page and JSON configuration API.
- Configuration is stored in `config.json` and saving settings restarts the runtime immediately.
- Mailbox runtime state is stored separately in `state.json` with `mail_present` and `last_updated`.
- The configuration page no longer shows a separate runtime status badge.
- The app logs each normalized Hue event when it is received.
- The mock Hue Bridge is HTTP-only and serves both `/eventstream/clip/v2` and minimal `/clip/v2/resource` endpoints for local integration testing.

## Configuration File

- `config.json` stores:
- `hue_base_url`: full bridge URL such as `http://127.0.0.1:8000` for the mock bridge.
- `hue_api_token`: Hue application key.
- `hue_contact_id`: Hue `contact` resource ID for the mailbox sensor.
- `hue_button_id`: Hue `button` resource ID for the clear action.
- `pixoo_host`: optional Pixoo64 host. If unset, the app auto-discovers Pixoo devices on the LAN and uses the first one found.

## Runtime State File

- `state.json` stores:
- `mail_present`: whether new mail is currently latched in the app state.
- `last_updated`: UTC timestamp of the last persisted mailbox state update.
- Hue button presses always clear the display and reset `mail_present` to avoid drift between persisted state and what is shown on the Pixoo.

## API

- `GET /`: configuration page that loads and saves settings through the API.
- `GET /api/config`: returns the current configuration.
- `PUT /api/config`: saves configuration and immediately restarts the runtime.
- `GET /api/discover/hue-bridges`: discovers Hue Bridges on the local network via the Hue discovery service.
- `GET /api/discover/pixoo`: discovers Pixoo devices on the local network.
- `POST /api/discover/hue-contacts`: discovers Hue contact sensors from the configured bridge.
- `POST /api/discover/hue-buttons`: discovers Hue button resources from the configured bridge.
- `POST /api/hue/create-token`: creates a Hue application key through the bridge link-button flow.
- `POST /api/test/hue-contact`: triggers the internal mail-detected flow without contacting the Hue bridge.
- `POST /api/test/hue-button`: triggers the internal clear flow without contacting the Hue bridge.

## Hue Token Flow

- Enter a Hue Bridge URL in `Hue Base URL`.
- Press the physical button on the Hue Bridge.
- Click `Create Token` in the UI.
- The UI fills `Hue API Token` when the bridge returns a new application key.
- Click `Save Settings` to persist the token into `config.json`.

## UI Test Buttons

- The `Test` button next to `Discover Contacts` triggers the internal `mail detected` flow.
- The `Test` button next to `Discover Buttons` triggers the internal `button pressed` flow.
- These do not contact the Hue bridge and are meant to test the Pixoo flow directly.
- Each button stays disabled until the corresponding configured resource ID is present.

## Pixoo Behavior

- `show_new_mail()` runs a continuously looping modern envelope-opening animation to attract attention.
- The fully open envelope frame is held slightly longer than the transition frames.
- `clear()` clears the Pixoo display to black.
- Pixoo discovery prefers the library's built-in discovery and falls back to the Divoom LAN discovery endpoint when needed.

## Mock Bridge Example

- Start the mock bridge: `uv run mailbox-notify-mock-hue --port 8000 --token mock-hue-token`
- Use `o` to simulate `contact_report.state == contact` and `b` to simulate `button.button_report.event == initial_press`
- Update `config.json` or `PUT /api/config` with:
- `hue_base_url=http://127.0.0.1:8000`
- `hue_api_token=mock-hue-token`
- `hue_contact_id=mock-contact-id`
- `hue_button_id=mock-button-id`

## Next steps

- Improve the UI layout and polish discovery/result states.
