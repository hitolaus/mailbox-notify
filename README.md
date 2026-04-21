# mailbox-notify

Local Philips Hue contact sensor to Divoom Pixoo64 display bridge.

## What it does

- Listen to Philips Hue API v2 event stream updates from one Hue Bridge.
- Detect when the mailbox contact sensor changes state.
- Show a persistent new-mail icon on the Pixoo64.
- Clear the display only when a Philips Hue button is pressed.
- Persist mailbox state in `state.json` and restore the Pixoo display on restart.

## Assumptions

- The app runs locally on the same network as both devices.

## Stack

- Python 3.11+
- `uv` for dependency management and environment sync.
- `aiohue` for Philips Hue v2 and event-stream handling.
- `pixoo` for Pixoo64 device control.
- FastAPI and Uvicorn for the local web UI and JSON API.

## Getting Started

- Install `uv` if needed: `brew install uv`
- Sync dependencies: `uv sync --locked`
- Run the test suite: `uv run -m unittest discover -s tests`
- Run the mock Hue bridge: `uv run mailbox-notify-mock-hue`
- Run the app: `uv run mailbox-notify`
- Open `http://127.0.0.1:8000/`
- The app creates `config.json` and `state.json` in the project root on first start.

## Runtime Model

- The FastAPI app serves the configuration page at `/` and manages the mailbox runtime in-process.
- Saving configuration through the UI or `PUT /api/config` restarts the runtime immediately.
- The runtime only starts when these Hue settings are present: `hue_base_url`, `hue_api_token`, `hue_contact_id`, and `hue_button_id`.
- `pixoo_host` is optional. If it is empty, the app tries Pixoo library discovery first and falls back to the Divoom LAN discovery API.
- On startup, the runtime reads `state.json` and immediately syncs the Pixoo display to the persisted `mail_present` value.

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
- Persistent files are created in `./data/`: `config.json`, `state.json`.

### Update

- Pull the latest changes: `git pull`
- Rebuild and restart: `docker compose up -d --build`

### Stop

- Stop the service: `docker compose down`

### Notes

- The container sets `MAILBOX_NOTIFY_CONFIG_PATH=/data/config.json`.
- The container sets `MAILBOX_NOTIFY_STATE_PATH=/data/state.json`.
- The container sets `MAILBOX_NOTIFY_HOST=0.0.0.0`.
- The container sets `MAILBOX_NOTIFY_PORT=8000`.
- Linux host networking is the supported deployment mode.
- For stable long-running operation, save explicit `hue_base_url` and `pixoo_host` values once initial setup is complete.


## Configuration

- `config.json` stores `hue_base_url`: full bridge URL such as `http://127.0.0.1:8000` for the mock bridge.
- `config.json` stores `hue_api_token`: Hue application key.
- `config.json` stores `hue_contact_id`: Hue `contact` resource ID for the mailbox sensor.
- `config.json` stores `hue_button_id`: Hue `button` resource ID for the clear action.
- `config.json` stores `pixoo_host`: optional Pixoo64 host. If unset, the runtime auto-discovers a device.

## Runtime State

- `state.json` stores `mail_present`: whether new mail is currently latched in the app state.
- `state.json` stores `last_updated`: UTC timestamp of the last persisted mailbox state update.
- Hue button presses always clear the display and reset `mail_present` to avoid drift between persisted state and what is shown on the Pixoo.

## Environment Variables

- `MAILBOX_NOTIFY_CONFIG_PATH`: override the config file path.
- `MAILBOX_NOTIFY_STATE_PATH`: override the runtime state file path.
- `MAILBOX_NOTIFY_HOST`: override the FastAPI/Uvicorn bind host.
- `MAILBOX_NOTIFY_PORT`: override the FastAPI/Uvicorn bind port.

## API

- `GET /`: configuration page that loads and saves settings through the API.
- `GET /api/config`: returns the current configuration.
- `PUT /api/config`: saves configuration and immediately restarts the runtime.
- `GET /api/discover/hue-bridges`: discovers Hue Bridges on the local network via the Hue discovery service.
- `GET /api/discover/pixoo`: discovers Pixoo devices on the local network and returns normalized device metadata.
- `POST /api/discover/hue-contacts`: discovers Hue contact sensors from the configured bridge.
- `POST /api/discover/hue-buttons`: discovers Hue button resources from the configured bridge.
- `POST /api/hue/create-token`: creates a Hue application key through the bridge link-button flow and returns `token` plus `clientkey`.
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
- The test endpoints still require an active runtime, so save a complete configuration first.

## Pixoo Behavior

- `show_new_mail()` runs a continuously looping modern envelope-opening animation to attract attention.
- The fully open envelope frame is held slightly longer than the transition frames.
- `clear()` clears the Pixoo display to black.
- Runtime Pixoo discovery prefers the library's built-in discovery and falls back to the Divoom LAN discovery endpoint when needed.
- The public discovery API currently uses the Divoom LAN discovery endpoint directly.

## Mock Bridge Example

- Start the mock bridge: `uv run mailbox-notify-mock-hue --port 8000 --token mock-hue-token`
- Use `o` to simulate `contact_report.state == contact` and `b` to simulate `button.button_report.event == initial_press`
- The mock bridge also exposes `/clip/v2/resource/device`, `/clip/v2/resource/contact`, `/clip/v2/resource/button`, and `/clip/v2/resource` for UI discovery flows.
- Update `config.json` or `PUT /api/config` with `hue_base_url=http://127.0.0.1:8000`.
- Update `config.json` or `PUT /api/config` with `hue_api_token=mock-hue-token`.
- Update `config.json` or `PUT /api/config` with `hue_contact_id=mock-contact-id`.
- Update `config.json` or `PUT /api/config` with `hue_button_id=mock-button-id`.
