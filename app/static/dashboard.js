let portals = [];
const revealed = new Map();
let loading = false;

const grid = document.getElementById("otp-grid");
const refreshButton = document.getElementById("refresh-button");
const csrfToken = window.otpPortalCsrfToken || "";

function secondsLeft(item) {
  const now = Math.floor(Date.now() / 1000);
  const serverNow = Number(item.server_time || item.timestamp || now);
  const offset = Number.isFinite(item.clockOffsetSeconds)
    ? item.clockOffsetSeconds
    : now - serverNow;
  item.clockOffsetSeconds = offset;
  return Math.max(0, Number(item.expires_at) - (now - offset));
}

function render() {
  if (!portals.length) {
    grid.innerHTML = '<div class="empty-state">No OTP portals are assigned to you.</div>';
    return;
  }

  grid.innerHTML = portals.map((portal) => {
    const item = revealed.get(portal.portal_name);
    if (item && secondsLeft(item) > 0) {
      const left = secondsLeft(item);
      const percent = Math.max(0, Math.min(100, (left / item.period) * 100));
      return `
        <article class="otp-card">
          <header>
            <div>
              <h2>${escapeHtml(portal.display_name)}</h2>
              <div class="portal-name">/otp/${escapeHtml(portal.portal_name)}</div>
            </div>
            <strong>${left}s</strong>
          </header>
          <div class="otp-code">${escapeHtml(item.otp)}</div>
          <button type="button" class="secondary-button" data-copy="${escapeHtml(portal.portal_name)}">
            Copy code
          </button>
          <div class="countdown-track">
            <div class="countdown-bar" role="progressbar" aria-valuemin="0" aria-valuemax="${item.period}" aria-valuenow="${left}" style="width:${percent}%"></div>
          </div>
          <div class="countdown-text" role="timer" aria-live="polite">Code hides when this window ends.</div>
        </article>
      `;
    }

    revealed.delete(portal.portal_name);
    return `
      <article class="otp-card">
        <h2>${escapeHtml(portal.display_name)}</h2>
        <div class="portal-name">/otp/${escapeHtml(portal.portal_name)}</div>
        <button type="button" class="secondary-button" data-reveal="${escapeHtml(portal.portal_name)}">
          Reveal code
        </button>
      </article>
    `;
  }).join("");

  grid.querySelectorAll("[data-reveal]").forEach((button) => {
    button.addEventListener("click", () => revealPortal(button.dataset.reveal, button));
  });
  grid.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", () => copyPortal(button.dataset.copy, button));
  });
}

async function loadPortals() {
  if (loading || !navigator.onLine) {
    if (!navigator.onLine) {
      grid.innerHTML = '<div class="error">You are offline. Codes remain hidden until the connection is restored.</div>';
    }
    return;
  }
  loading = true;
  try {
    const response = await fetch("/api/ui/portals", { cache: "no-store" });
    if (response.status === 401) {
      window.location.href = "/login";
      return;
    }
    if (!response.ok) {
      throw new Error("portal metadata request failed");
    }
    const payload = await response.json();
    portals = payload.portals || [];
    revealed.clear();
    render();
  } catch (_error) {
    revealed.clear();
    grid.innerHTML = '<div class="error">Unable to load assigned portals. Try again.</div>';
  } finally {
    loading = false;
  }
}

async function revealPortal(portalName, button) {
  button.disabled = true;
  try {
    const response = await fetch(`/api/ui/portals/${encodeURIComponent(portalName)}/otp`, {
      method: "POST",
      headers: {
        "X-CSRF-Token": csrfToken,
        "Cache-Control": "no-store",
      },
      cache: "no-store",
    });
    if (response.status === 401) {
      window.location.href = "/login";
      return;
    }
    if (!response.ok) {
      throw new Error("OTP reveal request failed");
    }
    const item = await response.json();
    revealed.set(portalName, item);
    render();
  } catch (_error) {
    button.disabled = false;
    button.textContent = "Reveal failed; retry";
  }
}

async function copyPortal(portalName, button) {
  const item = revealed.get(portalName);
  if (!item || secondsLeft(item) <= 0) {
    revealed.delete(portalName);
    render();
    return;
  }
  try {
    await navigator.clipboard.writeText(item.otp);
    button.textContent = "Copied";
    window.setTimeout(() => {
      if (button.isConnected) button.textContent = "Copy code";
    }, 1200);
  } catch (_error) {
    button.textContent = "Copy unavailable";
  }
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

setInterval(() => {
  for (const [portalName, item] of revealed.entries()) {
    if (secondsLeft(item) <= 0) {
      revealed.delete(portalName);
    }
  }
  render();
}, 1000);

refreshButton.addEventListener("click", loadPortals);
window.addEventListener("online", loadPortals);
window.addEventListener("offline", () => {
  revealed.clear();
  render();
});
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    revealed.clear();
    render();
  } else {
    loadPortals();
  }
});
window.addEventListener("pagehide", () => revealed.clear());
loadPortals();
