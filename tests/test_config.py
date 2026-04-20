from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from mailbox_notify.config import (
    Config,
    default_config,
    ensure_config_file,
    is_config_complete,
    load_config,
    save_config,
)


class ConfigTests(unittest.TestCase):
    def test_ensure_config_file_creates_defaults(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"

            config = ensure_config_file(config_path)

            self.assertTrue(config_path.exists())
            self.assertEqual(config, default_config())
            self.assertEqual(load_config(config_path), default_config())

    def test_save_and_load_config_round_trip(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config = Config(
                hue_base_url="http://127.0.0.1:8000",
                hue_api_token="token",
                hue_contact_id="contact-id",
                hue_button_id="button-id",
                pixoo_host="10.0.0.5",
            )

            save_config(config, config_path)

            self.assertEqual(load_config(config_path), config)

    def test_is_config_complete_requires_hue_fields_only(self) -> None:
        self.assertFalse(is_config_complete(default_config()))
        self.assertTrue(
            is_config_complete(
                Config(
                    hue_base_url="http://127.0.0.1:8000",
                    hue_api_token="token",
                    hue_contact_id="contact-id",
                    hue_button_id="button-id",
                    pixoo_host="",
                )
            )
        )
