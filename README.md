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
- Run the app: `uv run mailbox-notify`

## Intended structure

- `src/mailbox_notify/` for the application package.
- `tests/` for state and event handling tests.
- `AGENTS.md` for implementation guidance and project rules.

## Implementation notes

- Keep Hue-specific code isolated from Pixoo-specific code.
- Prefer async I/O throughout.
- Keep the state machine small and explicit: `mail_present` on sensor trigger, `cleared` on button press.
- Make display updates idempotent so repeated sensor events do not cause unnecessary redraws.

## Next steps

- Add Hue bridge config and auth handling.
- Implement event-stream subscription and mapping.
- Implement Pixoo display rendering and clear behavior.
- Add tests for state transitions.
