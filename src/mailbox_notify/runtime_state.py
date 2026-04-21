"""Runtime mailbox state persistence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path


STATE_PATH_ENV = "MAILBOX_NOTIFY_STATE_PATH"


def default_state_path() -> Path:
    configured_path = os.environ.get(STATE_PATH_ENV, "").strip()
    if configured_path:
        return Path(configured_path).expanduser()
    return Path(__file__).resolve().parents[2] / "state.json"


STATE_PATH = default_state_path()


@dataclass(frozen=True)
class RuntimeState:
    mail_present: bool
    last_updated: str


def default_runtime_state() -> RuntimeState:
    return RuntimeState(mail_present=False, last_updated="")


def ensure_runtime_state_file(state_path: Path = STATE_PATH) -> RuntimeState:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    if state_path.exists():
        return load_runtime_state(state_path)

    state = default_runtime_state()
    save_runtime_state(state, state_path)
    return state


def load_runtime_state(state_path: Path = STATE_PATH) -> RuntimeState:
    if not state_path.exists():
        return ensure_runtime_state_file(state_path)

    payload = json.loads(state_path.read_text())
    defaults = asdict(default_runtime_state())
    defaults.update(payload)
    return RuntimeState(
        mail_present=bool(defaults.get("mail_present", False)),
        last_updated=str(defaults.get("last_updated", "")).strip(),
    )


def save_runtime_state(state: RuntimeState, state_path: Path = STATE_PATH) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(asdict(state), indent=2, sort_keys=True) + "\n")


def updated_runtime_state(mail_present: bool) -> RuntimeState:
    return RuntimeState(mail_present=mail_present, last_updated=utc_timestamp())


def utc_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
