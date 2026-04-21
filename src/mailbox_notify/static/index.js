const liveDiscoverButtons = document.querySelectorAll('[data-live-discover]');
const resultPanels = document.querySelectorAll('.mock-results');
const configInputs = document.querySelectorAll('[data-config-key]');
const saveButton = document.getElementById('save-settings');
const resetButton = document.getElementById('reset-settings');
const feedback = document.getElementById('save-feedback');
const createTokenButton = document.getElementById('create-token');
const tokenInput = document.getElementById('hue-api-token');
const hueBaseUrlInput = document.getElementById('hue-base-url');
const contactIdInput = document.getElementById('hue-contact-id');
const buttonIdInput = document.getElementById('hue-button-id');
const tokenFeedback = document.getElementById('token-feedback');
const testContactButton = document.getElementById('test-contact');
const testButtonButton = document.getElementById('test-button');

function setFeedback(message, kind = '') {
  feedback.textContent = message;
  feedback.className = kind ? 'feedback ' + kind : 'feedback';
}

function setTokenFeedback(message, kind = '') {
  tokenFeedback.textContent = message;
  tokenFeedback.className = kind ? 'feedback ' + kind : 'feedback';
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
  updateTestButtons();
}

function updateTestButtons() {
  testContactButton.disabled = !contactIdInput.value.trim();
  testButtonButton.disabled = !buttonIdInput.value.trim();
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
    const isHueContacts = url.includes('/api/discover/hue-contacts');
    const isHueButtons = url.includes('/api/discover/hue-buttons');
    const loadingText = isPixoo
      ? 'Discovering Pixoo devices...'
      : isHueContacts
        ? 'Discovering contact sensors...'
        : isHueButtons
          ? 'Discovering buttons...'
          : 'Discovering bridges...';
    panel.innerHTML = '<div class="footnote">' + loadingText + '</div>';
    panel.classList.add('open');

    try {
      const options = {};
      if (isHueContacts || isHueButtons) {
        options.method = 'POST';
        options.headers = { 'Content-Type': 'application/json' };
        options.body = JSON.stringify({
          hue_base_url: hueBaseUrlInput.value.trim(),
          hue_api_token: tokenInput.value.trim(),
        });
      }

      const response = await fetch(url, options);
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || 'Discovery failed');
      }

      const resources = await response.json();
      if (!Array.isArray(resources) || resources.length === 0) {
        const emptyText = isPixoo
          ? 'No Pixoo devices found on the network.'
          : isHueContacts
            ? 'No contact sensors found on the bridge.'
            : isHueButtons
              ? 'No buttons found on the bridge.'
              : 'No Hue Bridges found on the network.';
        panel.innerHTML = '<div class="footnote">' + emptyText + '</div>';
        return;
      }

      panel.innerHTML = resources.map((resource) => {
        const value = isPixoo
          ? resource.host
          : (isHueContacts || isHueButtons)
            ? resource.id
            : resource.base_url;
        const title = isPixoo
          ? resource.name
          : (isHueContacts || isHueButtons)
            ? resource.name
            : 'Hue Bridge';
        const subtitle = isPixoo
          ? resource.host + ' · ' + resource.device_id
          : isHueContacts
            ? resource.id
            : isHueButtons
              ? resource.id + (resource.control_id ? ' · control ' + resource.control_id : '')
              : resource.internalipaddress + ' · ' + resource.id;
        return '<button type="button" class="mock-option" data-value="' + value + '">' +
          title +
          '<small>' + subtitle + '</small>' +
          '</button>';
      }).join('');
      bindResultOptions(panel);
      updateTestButtons();
    } catch (error) {
      panel.innerHTML = '<div class="footnote">' + (error.message || (isPixoo ? 'Unable to discover Pixoo devices right now.' : 'Unable to discover Hue resources right now.')) + '</div>';
    }
  });
});

async function triggerInternalTest(url, successMessage) {
  setFeedback('Triggering test...');
  try {
    const response = await fetch(url, { method: 'POST' });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || 'Unable to trigger test');
    }
    setFeedback(successMessage, 'success');
  } catch (error) {
    setFeedback(error.message || 'Unable to trigger test.', 'error');
  }
}

testContactButton.addEventListener('click', async () => {
  await triggerInternalTest('/api/test/hue-contact', 'Triggered contact test event.');
});

testButtonButton.addEventListener('click', async () => {
  await triggerInternalTest('/api/test/hue-button', 'Triggered button test event.');
});

contactIdInput.addEventListener('input', updateTestButtons);
buttonIdInput.addEventListener('input', updateTestButtons);

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
    setFeedback('Configuration loaded.');
  } catch (error) {
    setFeedback('Unable to load configuration.', 'error');
  } finally {
    updateTestButtons();
    setBusyState(false);
  }
})();
