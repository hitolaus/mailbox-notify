"""Application entry point and web server."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
from pathlib import Path
from typing import Protocol

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

from .config import (
    CONFIG_PATH,
    Config,
    ensure_config_file,
    is_config_complete,
    load_config,
    save_config,
)
from .hue import (
    AioHueClient,
    HueClient,
    HueTokenCreationError,
    create_hue_application_key,
    discover_hue_bridges,
)
from .pixoo import PixooDisplay, create_pixoo_display, discover_pixoo_devices
from .state import MailboxStateMachine


LOGGER = logging.getLogger(__name__)


INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Mailbox Notify</title>
  <style>
    :root {
      color-scheme: light dark;
      --bg: #f4f7fb;
      --panel: rgba(255, 255, 255, 0.88);
      --panel-border: rgba(15, 23, 42, 0.08);
      --text: #0f172a;
      --muted: #64748b;
      --accent: #2563eb;
      --accent-soft: rgba(37, 99, 235, 0.12);
      --input: rgba(248, 250, 252, 0.92);
      --shadow: 0 20px 60px rgba(15, 23, 42, 0.12);
    }

    @media (prefers-color-scheme: dark) {
      :root {
        --bg: #07111f;
        --panel: rgba(12, 19, 33, 0.88);
        --panel-border: rgba(148, 163, 184, 0.16);
        --text: #e5eefb;
        --muted: #93a5c3;
        --accent: #60a5fa;
        --accent-soft: rgba(96, 165, 250, 0.14);
        --input: rgba(15, 23, 42, 0.92);
        --shadow: 0 24px 80px rgba(2, 6, 23, 0.45);
      }
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(37, 99, 235, 0.18), transparent 28%),
        radial-gradient(circle at top right, rgba(14, 165, 233, 0.14), transparent 22%),
        var(--bg);
      color: var(--text);
      min-height: 100vh;
    }

    .shell {
      width: min(960px, calc(100vw - 32px));
      margin: 48px auto;
    }

    .hero {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 16px;
      margin-bottom: 24px;
    }

    .eyebrow {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 12px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }

    h1 {
      margin: 14px 0 8px;
      font-size: clamp(2rem, 5vw, 3.4rem);
      line-height: 1;
      letter-spacing: -0.04em;
    }

    .hero p {
      margin: 0;
      color: var(--muted);
      max-width: 680px;
      font-size: 1rem;
      line-height: 1.6;
    }

    .status-chip {
      padding: 12px 14px;
      border: 1px solid var(--panel-border);
      border-radius: 18px;
      background: var(--panel);
      box-shadow: var(--shadow);
      min-width: 180px;
      backdrop-filter: blur(18px);
    }

    .status-chip strong {
      display: block;
      margin-bottom: 6px;
      font-size: 13px;
    }

    .status-chip span {
      color: var(--muted);
      font-size: 14px;
    }

    .status-chip span.status-running {
      color: #16a34a;
    }

    .status-chip span.status-waiting {
      color: #d97706;
    }

    .status-chip span.status-error {
      color: #dc2626;
    }

    .panel {
      border: 1px solid var(--panel-border);
      border-radius: 28px;
      background: var(--panel);
      box-shadow: var(--shadow);
      backdrop-filter: blur(18px);
      padding: 28px;
    }

    .panel-grid {
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 28px;
    }

    .section + .section {
      margin-top: 28px;
    }

    .section-title {
      margin: 0 0 6px;
      font-size: 1.05rem;
      font-weight: 700;
    }

    .section-copy {
      margin: 0 0 18px;
      color: var(--muted);
      font-size: 0.95rem;
      line-height: 1.6;
    }

    .field-grid {
      display: grid;
      gap: 16px;
    }

    .field {
      display: grid;
      gap: 8px;
    }

    .field label {
      font-size: 13px;
      font-weight: 600;
      color: var(--muted);
    }

    input {
      width: 100%;
      padding: 14px 16px;
      border-radius: 16px;
      border: 1px solid var(--panel-border);
      background: var(--input);
      color: var(--text);
      font: inherit;
      outline: none;
      transition: border-color 0.16s ease, box-shadow 0.16s ease, transform 0.16s ease;
    }

    input:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 4px var(--accent-soft);
      transform: translateY(-1px);
    }

    .inline-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: start;
    }

    button {
      appearance: none;
      border: 0;
      border-radius: 14px;
      padding: 13px 16px;
      font: inherit;
      font-weight: 600;
      cursor: pointer;
      transition: transform 0.16s ease, opacity 0.16s ease, background 0.16s ease;
    }

    button:hover {
      transform: translateY(-1px);
    }

    .button-primary {
      background: linear-gradient(135deg, var(--accent), #38bdf8);
      color: white;
    }

    .button-secondary {
      background: var(--accent-soft);
      color: var(--accent);
    }

    .button-ghost {
      background: transparent;
      color: var(--muted);
      border: 1px solid var(--panel-border);
    }

    .mock-results {
      display: none;
      margin-top: 10px;
      padding: 10px;
      border: 1px solid var(--panel-border);
      border-radius: 16px;
      background: color-mix(in srgb, var(--panel) 84%, transparent);
      gap: 8px;
    }

    .mock-results.open {
      display: grid;
    }

    .mock-option {
      width: 100%;
      text-align: left;
      background: transparent;
      color: var(--text);
      border: 1px solid transparent;
      padding: 12px 12px;
    }

    .mock-option:hover {
      background: var(--accent-soft);
      border-color: color-mix(in srgb, var(--accent) 32%, transparent);
    }

    .mock-option small {
      display: block;
      margin-top: 4px;
      color: var(--muted);
    }

    .aside-card {
      border: 1px solid var(--panel-border);
      border-radius: 22px;
      padding: 18px;
      background: color-mix(in srgb, var(--panel) 90%, transparent);
    }

    .aside-card + .aside-card {
      margin-top: 14px;
    }

    .aside-card h3 {
      margin: 0 0 8px;
      font-size: 0.98rem;
    }

    .aside-card p,
    .aside-card li {
      color: var(--muted);
      font-size: 0.92rem;
      line-height: 1.6;
    }

    .aside-card ul {
      margin: 0;
      padding-left: 18px;
    }

    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-top: 24px;
      align-items: center;
    }

    .footnote {
      color: var(--muted);
      font-size: 0.9rem;
    }

    .feedback {
      min-height: 1.2rem;
      color: var(--muted);
      font-size: 0.9rem;
    }

    .feedback.success {
      color: #16a34a;
    }

    .feedback.error {
      color: #dc2626;
    }

    @media (max-width: 860px) {
      .shell {
        margin: 20px auto;
      }

      .hero {
        flex-direction: column;
      }

      .panel {
        padding: 20px;
        border-radius: 22px;
      }

      .panel-grid {
        grid-template-columns: 1fr;
      }

      .inline-row {
        grid-template-columns: 1fr;
      }

      button {
        width: 100%;
      }
    }
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div>
        <span class="eyebrow">Mailbox Notify</span>
        <h1>Configure your mailbox display</h1>
        <p>Mock settings interface for the next step of the app. Discovery buttons use placeholder data for now so the layout and interaction flow can be reviewed before wiring the backend.</p>
      </div>
      <aside class="status-chip">
        <strong>Runtime</strong>
        <span id="runtime-status">Loading configuration...</span>
      </aside>
    </section>

    <section class="panel">
      <div class="panel-grid">
        <div>
          <section class="section">
            <h2 class="section-title">Hue Bridge</h2>
            <p class="section-copy">Point the runtime at a Hue Bridge or the local mock bridge, then pick the contact sensor and clear button you want to use.</p>
            <div class="field-grid">
              <div class="field">
                <label for="hue-base-url">Hue Base URL</label>
                <div class="inline-row">
                  <input id="hue-base-url" name="hue_base_url" data-config-key="hue_base_url" type="text" placeholder="http://127.0.0.1:8000">
                  <button type="button" class="button-secondary" data-live-discover="hue-bridge-results" data-live-discover-url="/api/discover/hue-bridges">Discover Bridges</button>
                </div>
                <div id="hue-bridge-results" class="mock-results" data-input-target="hue-base-url"></div>
              </div>
              <div class="field">
                <label for="hue-api-token">Hue API Token</label>
                <div class="inline-row">
                  <input id="hue-api-token" name="hue_api_token" data-config-key="hue_api_token" type="text" placeholder="Paste application key">
                  <button id="create-token" type="button" class="button-secondary">Create Token</button>
                </div>
                <div id="token-feedback" class="feedback">Press the bridge button, then click Create Token.</div>
              </div>
              <div class="field">
                <label for="hue-contact-id">Hue Contact ID</label>
                <div class="inline-row">
                  <input id="hue-contact-id" name="hue_contact_id" data-config-key="hue_contact_id" type="text" placeholder="contact resource id">
                  <button type="button" class="button-secondary" data-discover-target="contact-results">Discover Contacts</button>
                </div>
                <div id="contact-results" class="mock-results" data-input-target="hue-contact-id">
                  <button type="button" class="mock-option" data-value="contact-id-1">Mailbox Contact<small>contact-id-1</small></button>
                  <button type="button" class="mock-option" data-value="contact-id-2">Door Sensor<small>contact-id-2</small></button>
                </div>
              </div>
              <div class="field">
                <label for="hue-button-id">Hue Button ID</label>
                <div class="inline-row">
                  <input id="hue-button-id" name="hue_button_id" data-config-key="hue_button_id" type="text" placeholder="button resource id">
                  <button type="button" class="button-secondary" data-discover-target="button-results">Discover Buttons</button>
                </div>
                <div id="button-results" class="mock-results" data-input-target="hue-button-id">
                  <button type="button" class="mock-option" data-value="button-id-1">Mailbox Clear Button<small>button-id-1</small></button>
                  <button type="button" class="mock-option" data-value="button-id-2">Kitchen Button<small>button-id-2</small></button>
                </div>
              </div>
            </div>
          </section>

          <section class="section">
            <h2 class="section-title">Pixoo Display</h2>
            <p class="section-copy">Enter a Pixoo IP manually or use discovery to select one of the devices found on the local network.</p>
            <div class="field-grid">
              <div class="field">
                <label for="pixoo-host">Pixoo Host</label>
                <div class="inline-row">
                  <input id="pixoo-host" name="pixoo_host" data-config-key="pixoo_host" type="text" placeholder="10.0.0.47">
                  <button type="button" class="button-secondary" data-live-discover="pixoo-results" data-live-discover-url="/api/discover/pixoo">Discover Pixoo</button>
                </div>
                <div id="pixoo-results" class="mock-results" data-input-target="pixoo-host"></div>
              </div>
            </div>
          </section>

          <div class="actions">
            <button id="save-settings" type="button" class="button-primary">Save Settings</button>
            <button id="reset-settings" type="button" class="button-ghost">Reset</button>
            <span id="save-feedback" class="feedback">Ready.</span>
          </div>
        </div>

        <aside>
          <section class="aside-card">
            <h3>What this mock demonstrates</h3>
            <p>The page now loads and saves the current JSON config directly through the API. Discovery for Hue Bridges and Pixoo devices is live, while contact and button discovery remains mocked for now.</p>
          </section>
          <section class="aside-card">
            <h3>Planned discovery flow</h3>
            <ul>
              <li>Pixoo discovery will list LAN devices and let you fill the host field.</li>
              <li>Hue discovery will query the configured bridge and list contact sensors and buttons.</li>
              <li>Saving settings will immediately restart the runtime with the new configuration.</li>
            </ul>
          </section>
        </aside>
      </div>
    </section>
  </main>

  <script>
    const discoverButtons = document.querySelectorAll('[data-discover-target]');
    const liveDiscoverButtons = document.querySelectorAll('[data-live-discover]');
    const resultPanels = document.querySelectorAll('.mock-results');
    const configInputs = document.querySelectorAll('[data-config-key]');
    const runtimeStatus = document.getElementById('runtime-status');
    const saveButton = document.getElementById('save-settings');
    const resetButton = document.getElementById('reset-settings');
    const feedback = document.getElementById('save-feedback');
    const createTokenButton = document.getElementById('create-token');
    const tokenInput = document.getElementById('hue-api-token');
    const hueBaseUrlInput = document.getElementById('hue-base-url');
    const tokenFeedback = document.getElementById('token-feedback');

    function setFeedback(message, kind = '') {
      feedback.textContent = message;
      feedback.className = kind ? 'feedback ' + kind : 'feedback';
    }

    function setTokenFeedback(message, kind = '') {
      tokenFeedback.textContent = message;
      tokenFeedback.className = kind ? 'feedback ' + kind : 'feedback';
    }

    function setRuntimeStatus(configured, running) {
      runtimeStatus.className = '';
      if (running) {
        runtimeStatus.textContent = 'Running';
        runtimeStatus.classList.add('status-running');
        return;
      }
      if (configured) {
        runtimeStatus.textContent = 'Configured but stopped';
        runtimeStatus.classList.add('status-error');
        return;
      }
      runtimeStatus.textContent = 'Waiting for configuration';
      runtimeStatus.classList.add('status-waiting');
    }

    function setBusyState(isBusy, label = 'Save Settings') {
      saveButton.disabled = isBusy;
      resetButton.disabled = isBusy;
      saveButton.textContent = isBusy ? label : 'Save Settings';
    }

    function collectConfig() {
      const payload = {};
      configInputs.forEach((input) => {
        payload[input.dataset.configKey] = input.value.trim();
      });
      return payload;
    }

    function applyConfig(config) {
      configInputs.forEach((input) => {
        input.value = config[input.dataset.configKey] || '';
      });
    }

    async function loadStatus() {
      const response = await fetch('/api/status');
      if (!response.ok) {
        throw new Error('Unable to load status');
      }
      const status = await response.json();
      setRuntimeStatus(status.configured, status.running);
      return status;
    }

    async function loadConfig() {
      const response = await fetch('/api/config');
      if (!response.ok) {
        throw new Error('Unable to load configuration');
      }
      const config = await response.json();
      applyConfig(config);
      return config;
    }

    function closeOtherPanels(openPanelId) {
      resultPanels.forEach((panel) => {
        if (panel.id !== openPanelId) {
          panel.classList.remove('open');
        }
      });
    }

    discoverButtons.forEach((button) => {
      button.addEventListener('click', () => {
        const targetId = button.dataset.discoverTarget;
        const panel = document.getElementById(targetId);
        if (!panel) {
          return;
        }
        const willOpen = !panel.classList.contains('open');
        closeOtherPanels(targetId);
        panel.classList.toggle('open', willOpen);
      });
    });

    function bindResultOptions(panel) {
      const input = document.getElementById(panel.dataset.inputTarget || '');
      panel.querySelectorAll('.mock-option').forEach((option) => {
        option.addEventListener('click', () => {
          if (input) {
            input.value = option.dataset.value || '';
          }
          panel.classList.remove('open');
        });
      });
    }

    resultPanels.forEach((panel) => {
      bindResultOptions(panel);
    });

    liveDiscoverButtons.forEach((button) => {
      button.addEventListener('click', async () => {
        const panel = document.getElementById(button.dataset.liveDiscover || '');
        const url = button.dataset.liveDiscoverUrl;
        if (!panel || !url) {
          return;
        }

        closeOtherPanels(panel.id);
        const isPixoo = url.includes('/api/discover/pixoo');
        panel.innerHTML = '<div class="footnote">' + (isPixoo ? 'Discovering Pixoo devices...' : 'Discovering bridges...') + '</div>';
        panel.classList.add('open');

        try {
          const response = await fetch(url);
          if (!response.ok) {
            throw new Error('Discovery failed');
          }

          const bridges = await response.json();
          if (!Array.isArray(bridges) || bridges.length === 0) {
            panel.innerHTML = '<div class="footnote">' + (isPixoo ? 'No Pixoo devices found on the network.' : 'No Hue Bridges found on the network.') + '</div>';
            return;
          }

          panel.innerHTML = bridges.map((bridge) => {
            const value = isPixoo ? bridge.host : bridge.base_url;
            const title = isPixoo ? bridge.name : 'Hue Bridge';
            const subtitle = isPixoo
              ? bridge.host + ' · ' + bridge.device_id
              : bridge.internalipaddress + ' · ' + bridge.id;
            return '<button type="button" class="mock-option" data-value="' + value + '">' +
              title +
              '<small>' + subtitle + '</small>' +
              '</button>';
          }).join('');
          bindResultOptions(panel);
        } catch (error) {
          panel.innerHTML = '<div class="footnote">' + (isPixoo ? 'Unable to discover Pixoo devices right now.' : 'Unable to discover Hue Bridges right now.') + '</div>';
        }
      });
    });

    saveButton.addEventListener('click', async () => {
      setBusyState(true, 'Saving...');
      setFeedback('Saving settings...');
      try {
        const response = await fetch('/api/config', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(collectConfig()),
        });
        if (!response.ok) {
          throw new Error('Unable to save settings');
        }
        const payload = await response.json();
        applyConfig(payload.config || {});
        setRuntimeStatus(payload.configured, payload.running);
        setFeedback('Settings saved.', 'success');
      } catch (error) {
        setFeedback('Unable to save settings.', 'error');
      } finally {
        setBusyState(false);
      }
    });

    createTokenButton.addEventListener('click', async () => {
      const hueBaseUrl = hueBaseUrlInput.value.trim();
      if (!hueBaseUrl) {
        setTokenFeedback('Enter a Hue Base URL first.', 'error');
        return;
      }

      createTokenButton.disabled = true;
      createTokenButton.textContent = 'Creating...';
      setTokenFeedback('Press the bridge button, then wait for the token response...');
      try {
        const response = await fetch('/api/hue/create-token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ hue_base_url: hueBaseUrl }),
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.detail || 'Unable to create token');
        }
        tokenInput.value = payload.token || '';
        setTokenFeedback('Hue API token created. Save settings to persist it.', 'success');
      } catch (error) {
        setTokenFeedback(error.message || 'Unable to create Hue API token.', 'error');
      } finally {
        createTokenButton.disabled = false;
        createTokenButton.textContent = 'Create Token';
      }
    });

    resetButton.addEventListener('click', async () => {
      setBusyState(true, 'Loading...');
      setFeedback('Reloading saved settings...');
      try {
        await loadConfig();
        await loadStatus();
        setFeedback('Reloaded saved settings.');
      } catch (error) {
        setFeedback('Unable to reload saved settings.', 'error');
      } finally {
        setBusyState(false);
      }
    });

    (async () => {
      setBusyState(true, 'Loading...');
      setFeedback('Loading configuration...');
      try {
        await loadConfig();
        await loadStatus();
        setFeedback('Configuration loaded.');
      } catch (error) {
        setRuntimeStatus(false, false);
        setFeedback('Unable to load configuration.', 'error');
      } finally {
        setBusyState(false);
      }
    })();
  </script>
</body>
</html>
"""


class RuntimeManager(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def restart(self, config: Config | None = None) -> None: ...

    def status(self) -> dict[str, bool]: ...


class ConfigPayload(BaseModel):
    hue_base_url: str = ""
    hue_api_token: str = ""
    hue_contact_id: str = ""
    hue_button_id: str = ""
    pixoo_host: str = ""

    def to_config(self) -> Config:
        data = {key: value.strip() for key, value in self.model_dump().items()}
        return Config(**data)


class HueBridgePayload(BaseModel):
    id: str
    internalipaddress: str
    base_url: str


class PixooDevicePayload(BaseModel):
    name: str
    host: str
    device_id: str
    device_mac: str
    hardware: str


class CreateHueTokenPayload(BaseModel):
    hue_base_url: str = ""


class HueTokenResponse(BaseModel):
    token: str
    clientkey: str = ""


class MailboxRuntimeManager:
    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._config = ensure_config_file(config_path)

    async def start(self) -> None:
        async with self._lock:
            self._config = load_config(self._config_path)
            await self._start_locked(self._config)

    async def stop(self) -> None:
        async with self._lock:
            await self._stop_locked()

    async def restart(self, config: Config | None = None) -> None:
        async with self._lock:
            self._config = load_config(self._config_path) if config is None else config
            await self._stop_locked()
            await self._start_locked(self._config)

    def status(self) -> dict[str, bool]:
        return {
            "configured": is_config_complete(self._config),
            "running": self._task is not None and not self._task.done(),
        }

    async def _start_locked(self, config: Config) -> None:
        if not is_config_complete(config):
            LOGGER.info(
                "Mailbox runtime not started because configuration is incomplete"
            )
            self._task = None
            return
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(run_mailbox_runtime(config))

    async def _stop_locked(self) -> None:
        if self._task is None:
            return
        task = self._task
        self._task = None
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def serve(
    hue_client: HueClient,
    display: PixooDisplay,
    state_machine: MailboxStateMachine,
) -> None:
    await hue_client.connect()
    try:
        async for event in hue_client.events():
            LOGGER.info("Received Hue event: %s", event.kind.name)
            await state_machine.handle(event, display)
    finally:
        await hue_client.disconnect()


async def run_mailbox_runtime(config: Config) -> None:
    display = await create_pixoo_display(config.pixoo_host)
    state_machine = MailboxStateMachine()

    while True:
        hue_client = AioHueClient(
            base_url=config.hue_base_url,
            api_token=config.hue_api_token,
            contact_id=config.hue_contact_id,
            button_id=config.hue_button_id,
        )
        try:
            await serve(hue_client, display, state_machine)
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("Hue stream failed, reconnecting")
            await asyncio.sleep(5)


def create_app(config_path: Path = CONFIG_PATH) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ensure_config_file(config_path)
        app.state.runtime_manager = MailboxRuntimeManager(config_path)
        await app.state.runtime_manager.start()
        try:
            yield
        finally:
            await app.state.runtime_manager.stop()

    app = FastAPI(lifespan=lifespan)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return INDEX_HTML

    @app.get("/api/config")
    async def get_config() -> ConfigPayload:
        return ConfigPayload(**load_config(config_path).__dict__)

    @app.put("/api/config")
    async def put_config(payload: ConfigPayload) -> dict[str, object]:
        config = payload.to_config()
        save_config(config, config_path)
        await app.state.runtime_manager.restart(config)
        return {"config": payload.model_dump(), **app.state.runtime_manager.status()}

    @app.get("/api/status")
    async def get_status() -> dict[str, bool]:
        runtime_manager: RuntimeManager = app.state.runtime_manager
        return runtime_manager.status()

    @app.get("/api/discover/hue-bridges")
    async def get_hue_bridges() -> list[HueBridgePayload]:
        bridges = await discover_hue_bridges()
        return [HueBridgePayload(**bridge) for bridge in bridges]

    @app.get("/api/discover/pixoo")
    async def get_pixoo_devices() -> list[PixooDevicePayload]:
        devices = await discover_pixoo_devices()
        return [PixooDevicePayload(**device) for device in devices]

    @app.post("/api/hue/create-token")
    async def post_hue_create_token(
        payload: CreateHueTokenPayload,
    ) -> HueTokenResponse:
        try:
            created = await create_hue_application_key(payload.hue_base_url.strip())
        except HueTokenCreationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return HueTokenResponse(**created)

    return app


app = create_app()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
