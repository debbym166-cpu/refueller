/*
 * Redemption QR page.
 * - Shows a countdown to the visitor for reassurance only.
 * - The backend is always the source of truth for expiry: this script
 *   polls the redemption status endpoint, and the server decides
 *   PENDING / REDEEMED / EXPIRED independently of the browser's clock.
 */
document.addEventListener("DOMContentLoaded", function () {
  const root = document.getElementById("qr-root");
  if (!root) return;

  const statusUrl = root.dataset.statusUrl;
  const successUrl = root.dataset.successUrl;
  const countdownEl = document.getElementById("countdown");

  function tick(secondsRemaining) {
    if (!countdownEl) return;
    const m = Math.floor(secondsRemaining / 60).toString().padStart(2, "0");
    const s = Math.floor(secondsRemaining % 60).toString().padStart(2, "0");
    countdownEl.textContent = `${m}:${s}`;
  }

  let localSeconds = parseInt(root.dataset.secondsRemaining || "0", 10);
  tick(localSeconds);

  const localTimer = setInterval(function () {
    localSeconds = Math.max(0, localSeconds - 1);
    tick(localSeconds);
    if (localSeconds <= 0) clearInterval(localTimer);
  }, 1000);

  function poll() {
    fetch(statusUrl)
      .then((r) => r.json())
      .then((data) => {
        if (data.status === "REDEEMED") {
          window.location = successUrl;
        } else if (data.status === "EXPIRED") {
          window.location.reload();
        } else if (typeof data.seconds_remaining === "number") {
          localSeconds = data.seconds_remaining;
        }
      })
      .catch(() => {});
  }

  poll();
  setInterval(poll, 4000);
});
