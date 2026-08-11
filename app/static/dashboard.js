let otpItems = [];
let refreshTimer = null;

const grid = document.getElementById("otp-grid");
const refreshButton = document.getElementById("refresh-button");

function secondsLeft(item) {
  const now = Math.floor(Date.now() / 1000);
  const elapsed = Math.max(0, now - item.timestamp);
  return Math.max(0, item.valid_for_seconds - elapsed);
}

function render() {
  if (!otpItems.length) {
    grid.innerHTML = '<div class="empty-state">No OTP portals are active.</div>';
    return;
  }

  grid.innerHTML = otpItems.map((item) => {
    const left = secondsLeft(item);
    const percent = Math.max(0, Math.min(100, (left / item.period) * 100));
    return `
      <article class="otp-card">
        <header>
          <div>
            <h2>${escapeHtml(item.display_name)}</h2>
            <div class="portal-name">/otp/${escapeHtml(item.portal_name)}</div>
          </div>
          <strong>${left}s</strong>
        </header>
        <div class="otp-code">${escapeHtml(item.otp)}</div>
        <div class="countdown-track">
          <div class="countdown-bar" style="width:${percent}%"></div>
        </div>
        <div class="countdown-text">Next MFA code after this window ends</div>
      </article>
    `;
  }).join("");
}

function scheduleNextFetch() {
  if (refreshTimer) {
    clearTimeout(refreshTimer);
  }
  if (!otpItems.length) {
    return;
  }
  const shortest = Math.min(...otpItems.map(secondsLeft));
  refreshTimer = setTimeout(loadOtps, Math.max(1, shortest + 1) * 1000);
}

async function loadOtps() {
  const response = await fetch("/api/ui/otps", { cache: "no-store" });
  if (response.status === 401) {
    window.location.href = "/login";
    return;
  }
  const payload = await response.json();
  otpItems = payload.otps || [];
  render();
  scheduleNextFetch();
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

setInterval(render, 1000);
refreshButton.addEventListener("click", loadOtps);
loadOtps();
