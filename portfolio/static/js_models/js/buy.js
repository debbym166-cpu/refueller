/*
 * Buy Litres page.
 * - Quick-amount pills fill the litres input.
 * - The price total shown here is just a preview for the user - the
 *   backend recalculates it from the current FuelPrice when the form is
 *   submitted, so nothing here is trusted for the actual charge.
 */
document.addEventListener("DOMContentLoaded", function () {
  const input = document.getElementById("id_litres");
  const pills = document.querySelectorAll("[data-quick-litres]");
  const totalEl = document.getElementById("calc-total");
  const lineEl = document.getElementById("calc-line");
  const payBtn = document.getElementById("pay-btn");
  const form = document.getElementById("purchase-form");
  const overlay = document.getElementById("processing-overlay");

  if (!input) return;

  const pricePerLitre = parseFloat(input.dataset.price || "0");

  function formatNaira(value) {
    const rounded = Math.round(value * 100) / 100;
    const isWhole = rounded === Math.trunc(rounded);
    return "₦" + rounded.toLocaleString("en-NG", {
      minimumFractionDigits: isWhole ? 0 : 2,
      maximumFractionDigits: 2,
    });
  }

  function recalc() {
    const litres = parseFloat(input.value || "0");
    const total = litres > 0 ? litres * pricePerLitre : 0;

    if (totalEl) totalEl.textContent = formatNaira(total);
    if (lineEl) lineEl.textContent = `${litres || 0}L × ₦${pricePerLitre.toLocaleString("en-NG")}/L`;
    if (payBtn) payBtn.textContent = litres > 0 ? `Pay ${formatNaira(total)}` : "Pay";

    pills.forEach((pill) => {
      pill.classList.toggle("selected", parseFloat(pill.dataset.quickLitres) === litres);
    });
  }

  pills.forEach((pill) => {
    pill.addEventListener("click", function () {
      input.value = this.dataset.quickLitres;
      recalc();
    });
  });

  input.addEventListener("input", recalc);
  recalc();

  if (form && overlay) {
    form.addEventListener("submit", function () {
      overlay.classList.add("visible");
    });
  }
});
