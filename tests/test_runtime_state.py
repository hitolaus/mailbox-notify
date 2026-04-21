from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from mailbox_notify.runtime_state import (
    RuntimeState,
    default_runtime_state,
    ensure_runtime_state_file,
    load_runtime_state,
    save_runtime_state,
    updated_runtime_state,
)


class RuntimeStateTests(unittest.TestCase):
    def test_ensure_runtime_state_file_creates_defaults(self) -> None:
        with TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"

            state = ensure_runtime_state_file(state_path)

            self.assertTrue(state_path.exists())
            self.assertEqual(state, default_runtime_state())

    def test_save_and_load_runtime_state_round_trip(self) -> None:
        with TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            state = RuntimeState(mail_present=True, last_updated="2026-04-20T12:34:56Z")

            save_runtime_state(state, state_path)

            self.assertEqual(load_runtime_state(state_path), state)

    def test_updated_runtime_state_sets_timestamp(self) -> None:
        state = updated_runtime_state(True)

        self.assertTrue(state.mail_present)
        self.assertTrue(state.last_updated.endswith("Z"))
