const invoke = window.__TAURI__.core.invoke;
const status = document.getElementById('status');
const retry = document.getElementById('retry');
const openVault = document.getElementById('openVault');
const autostart = document.getElementById('autostart');
const keepRunning = document.getElementById('keepRunning');

async function refresh() {
  const state = await invoke('desktop_status');
  status.textContent = state.message;
  retry.hidden = !state.failed;
  openVault.hidden = !state.ready;
  autostart.checked = state.autostart;
  keepRunning.checked = state.keep_running;
}

retry.addEventListener('click', async () => {
  retry.hidden = true;
  await invoke('retry_backend');
  await refresh();
});
openVault.addEventListener('click', () => invoke('open_vault'));
autostart.addEventListener('change', async () => {
  await invoke('set_autostart', { enabled: autostart.checked });
  await refresh();
});
keepRunning.addEventListener('change', async () => {
  await invoke('set_keep_running', { enabled: keepRunning.checked });
  await refresh();
});
setInterval(() => refresh().catch(() => { status.textContent = 'Desktop service is unavailable.'; }), 1000);
refresh();
