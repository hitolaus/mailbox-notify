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
- Set `HUE_BASE_URL` or `HUE_BRIDGE_HOST`
- Set `HUE_API_TOKEN`, `HUE_CONTACT_ID`, and `HUE_BUTTON_ID`
- Run the mock Hue bridge: `uv run mailbox-notify-mock-hue`
- Run the app: `uv run mailbox-notify`

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
- The app logs each normalized Hue event when it is received.
- The mock Hue Bridge is HTTP-only and serves both `/eventstream/clip/v2` and minimal `/clip/v2/resource` endpoints for local integration testing.

## Environment

- `HUE_BASE_URL`: optional full bridge URL such as `http://127.0.0.1:8000` for the mock bridge.
- `HUE_BRIDGE_HOST`: optional host used when `HUE_BASE_URL` is not set. The app will use `https://<host>`.
- `HUE_API_TOKEN`: Hue application key.
- `HUE_CONTACT_ID`: Hue `contact` resource ID for the mailbox sensor.
- `HUE_BUTTON_ID`: Hue `button` resource ID for the clear action.
- `PIXOO_HOST`: optional Pixoo64 host. If unset, the app auto-discovers Pixoo devices on the LAN and uses the first one found.

## Pixoo Behavior

- `show_new_mail()` runs a continuously looping modern envelope-opening animation to attract attention.
- The fully open envelope frame is held slightly longer than the transition frames.
- `clear()` clears the Pixoo display to black.
- Pixoo discovery prefers the library's built-in discovery and falls back to the Divoom LAN discovery endpoint when needed.

## Mock Bridge Example

- Start the mock bridge: `uv run mailbox-notify-mock-hue --port 8000 --token mock-hue-token`
- Use `o` to simulate `contact_report.state == contact` and `b` to simulate `button.button_report.event == initial_press`
- Run the app against it with `HUE_BASE_URL=http://127.0.0.1:8000 HUE_API_TOKEN=mock-hue-token HUE_CONTACT_ID=mock-contact-id HUE_BUTTON_ID=mock-button-id uv run mailbox-notify`

## Next steps

- Implement Pixoo display rendering and clear behavior.
- Add tests for state transitions.
