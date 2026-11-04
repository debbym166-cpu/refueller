/*
 * Redeem Fuel page.
 * Shows a live preview of which litre lots a redemption would draw from,
 * using the same "earliest-expiring lot first" rule the backend uses.
 * This is just a preview for the user - the real deduction happens
 * server-side, inside a database transaction, when the redemption is
 * eventually confirmed by an attendant.
 */
document.addEventListener("DOMContentLoaded", function () {
  const input = document.getElementById("id_litres");
  const dataEl = document.getElementById("lots-data");
  const previewEl = document.getElementById("lots-preview");
  const availableEl = document.getElementById("available-figure");

  if (!input || !dataEl || !previewEl) return;

  const lots = JSON.parse(dataEl.textContent);
  const available = lots.reduce((sum, lot) => sum + lot.litres_remaining, 0);

  function render() {
    const requested = parseFloat(input.value || "0");

    if (!requested || requested <= 0) {
      previewEl.innerHTML = '<p class="text-faint text-sm">Enter a quantity to see which lots this will draw from.</p>';
      return;
    }

    let remaining = requested;
    const draws = [];
    for (const lot of lots) {
      if (remaining <= 0) break;
      const draw = Math.min(lot.litres_remaining, remaining);
      if (draw > 0) {
        draws.push({ litres: draw, label: lot.label, soonest: draws.length === 0 });
      }
      remaining -= draw;
    }

    if (draws.length === 0) {
      previewEl.innerHTML = '<p class="text-faint text-sm">No active litres available.</p>';
      return;
    }

    previewEl.innerHTML = draws.map((draw, i) => `
      <div class="row" style="padding: 12px 0; ${i > 0 ? 'border-top:1px solid var(--line-soft)' : ''}">
        <div>
          <div class="mono" style="font-weight:600;">${draw.litres.toFixed(3)}L</div>
          <div class="text-faint text-sm">${draw.label}</div>
        </div>
        <span class="badge ${draw.soonest ? 'badge-warning' : 'badge-healthy'}">
          ${draw.soonest ? 'Soonest' : 'Next lot'}
        </span>
      </div>
    `).join("");

    if (remaining > 0) {
      previewEl.innerHTML += `<p class="error-text mt-1">Only ${available.toFixed(3)}L available - reduce the quantity.</p>`;
    }
  }

  input.addEventListener("input", render);
  render();
});
