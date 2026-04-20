"""Configuration loading and persistence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.json"


@dataclass(frozen=True)
class Config:
    hue_base_url: str
    hue_api_token: str
    hue_contact_id: str
    hue_button_id: str
    pixoo_host: str


def default_config() -> Config:
    return Config(
        hue_base_url="",
        hue_api_token="",
        hue_contact_id="",
        hue_button_id="",
        pixoo_host="",
    )


def ensure_config_file(config_path: Path = CONFIG_PATH) -> Config:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists():
        return load_config(config_path)

    config = default_config()
    save_config(config, config_path)
    return config


def load_config(config_path: Path = CONFIG_PATH) -> Config:
    if not config_path.exists():
        return ensure_config_file(config_path)

    payload = json.loads(config_path.read_text())
    defaults = asdict(default_config())
    defaults.update(
        {key: str(value).strip() for key, value in payload.items() if key in defaults}
    )
    return Config(**defaults)


def save_config(config: Config, config_path: Path = CONFIG_PATH) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(asdict(config), indent=2, sort_keys=True) + "\n")


def is_config_complete(config: Config) -> bool:
    return all(
        (
            config.hue_base_url,
            config.hue_api_token,
            config.hue_contact_id,
            config.hue_button_id,
        )
    )
