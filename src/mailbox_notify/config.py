"""Configuration loading."""

from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Config:
    hue_base_url: str
    hue_api_token: str
    hue_contact_id: str
    hue_button_id: str
    pixoo_host: str


def load_config() -> Config:
    hue_base_url = os.environ.get("HUE_BASE_URL", "").strip()
    hue_bridge_host = os.environ.get("HUE_BRIDGE_HOST", "").strip()

    if not hue_base_url:
        if not hue_bridge_host:
            raise ValueError("Set HUE_BASE_URL or HUE_BRIDGE_HOST")
        hue_base_url = f"https://{hue_bridge_host}"

    return Config(
        hue_base_url=hue_base_url,
        hue_api_token=_required_env("HUE_API_TOKEN"),
        hue_contact_id=_required_env("HUE_CONTACT_ID"),
        hue_button_id=_required_env("HUE_BUTTON_ID"),
        pixoo_host=os.environ.get("PIXOO_HOST", "").strip(),
    )


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Set {name}")
    return value
