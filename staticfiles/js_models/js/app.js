/* ==========================================================================
   LitreVault — shared front-end behavior (plain JS, no framework/build step)
   Every hook below is opt-in via data-* attributes already present in the
   HTML, so wiring this to a real backend means: replace the fetch()/stash
   calls with real API calls and drop the data-demo-redirect navigation.
   ========================================================================== */
(function () {
  "use strict";

  /* ---------- helpers ---------- */
  function fmtNaira(n) {
    return Math.round(n).toLocaleString("en-NG");
  }
  function fmtLitres(n, dp) {
    return Number(n).toFixed(dp == null ? 3 : dp);
  }
  function qs(sel, ctx) { return (ctx || document).querySelector(sel); }
  function qsa(sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); }
  function addMonthsDays(daysFromNow) {
    var d = new Date();
    d.setDate(d.getDate() + Number(daysFromNow));
    return d.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
  }
  function stash(key, obj) {
    try { sessionStorage.setItem("lv_" + key, JSON.stringify(obj)); } catch (e) {}
  }
  function unstash(key) {
    try {
      var raw = sessionStorage.getItem("lv_" + key);
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
  }

  /* ==========================================================================
     1. Generic form demo-submit: any <form data-demo-redirect="..."> gets its
     submit intercepted, shows a brief pending state on the submit button,
     then navigates. In production, delete this block — real forms should
     just POST to `action` and let Django redirect server-side.
     ========================================================================== */
  function wireDemoForms() {
    qsa("form[data-demo-redirect]").forEach(function (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        if (form.checkValidity && !form.checkValidity()) {
          form.reportValidity();
          return;
        }
        var stashKind = form.getAttribute("data-stash");
        if (stashKind === "purchase") { stashPurchase(form); }
        if (stashKind === "redemption") { stashRedemption(form); }

        var btn = form.querySelector('button[type="submit"]');
        var originalLabel = btn ? btn.innerHTML : null;
        if (btn) { btn.disabled = true; btn.style.opacity = "0.7"; }
        setTimeout(function () {
          window.location.href = form.getAttribute("data-demo-redirect");
        }, 350);
      });
    });
  }

  /* ==========================================================================
     2. Password visibility toggle — works on any button[data-target="<id>"]
     ========================================================================== */
  function wirePasswordToggles() {
    qsa(".pw-toggle[data-target]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var input = document.getElementById(btn.getAttribute("data-target"));
        if (!input) return;
        var showing = input.type === "text";
        input.type = showing ? "password" : "text";
        btn.setAttribute("aria-label", showing ? "Show password" : "Hide password");
        btn.style.color = showing ? "var(--ink-faint)" : "var(--green-700)";
      });
    });
  }

  /* ==========================================================================
     3. "Continue with phone number" — demo: sends user into the OTP flow
     ========================================================================== */
  function wirePhoneLogin() {
    var btn = qs("[data-phone-login]");
    if (btn) {
      btn.addEventListener("click", function () {
        window.location.href = "06-auth-verify.html";
      });
    }
  }

  /* ==========================================================================
     4. OTP boxes — auto-advance, backspace-to-previous, auto-submit when full
     ========================================================================== */
  function wireOtp() {
    var group = qs("[data-otp-group]");
    if (!group) return;
    var boxes = qsa(".otp-box", group);
    boxes.forEach(function (box, i) {
      box.addEventListener("input", function () {
        box.value = box.value.replace(/[^0-9]/g, "").slice(0, 1);
        if (box.value && boxes[i + 1]) boxes[i + 1].focus();
        maybeSubmit();
      });
      box.addEventListener("keydown", function (e) {
        if (e.key === "Backspace" && !box.value && boxes[i - 1]) {
          boxes[i - 1].focus();
        }
      });
      box.addEventListener("paste", function (e) {
        var text = (e.clipboardData || window.clipboardData).getData("text").replace(/[^0-9]/g, "");
        if (!text) return;
        e.preventDefault();
        text.split("").forEach(function (ch, idx) {
          if (boxes[idx]) boxes[idx].value = ch;
        });
        var last = Math.min(text.length, boxes.length) - 1;
        if (boxes[last]) boxes[last].focus();
        maybeSubmit();
      });
    });
    function maybeSubmit() {
      if (boxes.every(function (b) { return b.value.length === 1; })) {
        var form = group.closest("form");
        if (form) form.requestSubmit ? form.requestSubmit() : form.dispatchEvent(new Event("submit", { cancelable: true }));
      }
    }
  }

  /* ==========================================================================
     5. Resend-code countdown
     ========================================================================== */
  function wireResend() {
    var btn = qs("[data-resend]");
    if (!btn) return;
    var display = qs("[data-resend-timer]", btn);
    var remaining = parseInt(btn.getAttribute("data-seconds"), 10) || 60;
    btn.disabled = true;
    var timer = setInterval(function () {
      remaining -= 1;
      var m = Math.floor(remaining / 60), s = remaining % 60;
      if (display) display.textContent = m + ":" + (s < 10 ? "0" : "") + s;
      if (remaining <= 0) {
        clearInterval(timer);
        btn.disabled = false;
        btn.textContent = "Resend code";
      }
    }, 1000);
    btn.addEventListener("click", function () {
      if (btn.disabled) return;
      remaining = 47;
      btn.disabled = true;
      btn.innerHTML = 'Resend in <span data-resend-timer>0:47</span>';
      wireResend(); // re-arm
    });
  }

  /* ==========================================================================
     6. Buy Litres — live calculation
     ========================================================================== */
  function wireBuyLitres() {
    var form = qs("[data-buy-form]");
    if (!form) return;
    var pricePerLitre = parseFloat(form.getAttribute("data-price-per-litre"));
    var validityDays = parseInt(form.getAttribute("data-validity-days"), 10);
    var litresInput = qs("[data-litres-input]", form);
    var chips = qsa(".chip[data-litres-preset]", form);

    function recalc() {
      var litres = parseFloat(litresInput.value) || 0;
      var total = litres * pricePerLitre;
      qsa("[data-litres-echo]").forEach(function (el) { el.textContent = fmtLitres(litres, litres % 1 === 0 ? 0 : 3); });
      qsa("[data-total-amount]").forEach(function (el) { el.textContent = fmtNaira(total); });
      var expiryEl = qs("[data-expiry-date]");
      if (expiryEl) expiryEl.textContent = addMonthsDays(validityDays);
      chips.forEach(function (c) {
        c.classList.toggle("active", parseFloat(c.getAttribute("data-litres-preset")) === litres);
      });
    }

    litresInput.addEventListener("input", recalc);
    chips.forEach(function (chip) {
      chip.addEventListener("click", function () {
        litresInput.value = chip.getAttribute("data-litres-preset");
        recalc();
      });
    });
    recalc();
  }

  function stashPurchase(form) {
    var pricePerLitre = parseFloat(form.getAttribute("data-price-per-litre"));
    var validityDays = parseInt(form.getAttribute("data-validity-days"), 10);
    var litres = parseFloat(qs("[data-litres-input]", form).value) || 0;
    var total = litres * pricePerLitre;
    stash("purchase", {
      litres: litres,
      pricePerLitre: pricePerLitre,
      amount: total,
      expiry: addMonthsDays(validityDays),
      reference: "LV-" + Math.floor(100000 + Math.random() * 899999)
    });
  }

  /* ==========================================================================
     7. Payment processing screen — auto-redirect + reflect stashed amount
     ========================================================================== */
  function wireProcessingScreen() {
    var el = qs("[data-auto-redirect]");
    if (!el) return;
    var purchase = unstash("purchase");
    if (purchase) {
      var amountEl = qs("[data-pending-amount]");
      if (amountEl) amountEl.textContent = "₦" + fmtNaira(purchase.amount);
    }
    var delay = parseInt(el.getAttribute("data-redirect-delay"), 10) || 1500;
    setTimeout(function () {
      window.location.href = el.getAttribute("data-auto-redirect");
    }, delay);
  }

  /* ==========================================================================
     8. Purchase success screen — reflect stashed purchase
     ========================================================================== */
  function wirePurchaseSuccess() {
    var root = qs("[data-purchase-success]");
    if (!root) return;
    var purchase = unstash("purchase");
    if (!purchase) return; // direct visit with no prior purchase — keep static demo values
    var litresWhole = qs("[data-result-litres]");
    var litres3dp = qs("[data-result-litres-3dp]");
    var price = qs("[data-result-price]");
    var amount = qs("[data-result-amount]");
    var expiry = qs("[data-result-expiry]");
    var ref = qs("[data-result-reference]");
    if (litresWhole) litresWhole.textContent = fmtLitres(purchase.litres, purchase.litres % 1 === 0 ? 0 : 3);
    if (litres3dp) litres3dp.textContent = fmtLitres(purchase.litres, 3);
    if (price) price.textContent = fmtNaira(purchase.pricePerLitre);
    if (amount) amount.textContent = fmtNaira(purchase.amount);
    if (expiry) expiry.textContent = purchase.expiry;
    if (ref) ref.textContent = purchase.reference;
  }

  /* ==========================================================================
     9. Redeem Fuel — station picker + live lot breakdown
     ========================================================================== */
  var USER_LOTS = [
    { litres: 8.5, label: "From lot expiring Sep 1 (soonest)", badge: "warning" },
    { litres: 20.0, label: "From lot purchased Aug 13", badge: "healthy" },
    { litres: 25.0, label: "From lot purchased Aug 20", badge: "healthy" }
  ];

  function badgeHtml(kind) {
    if (kind === "warning") {
      return '<span class="badge badge-warning"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="11" height="11"><path d="M12 4 3 20h18L12 4Z"/><path d="M12 10v4M12 17h.01"/></svg> Expiring soon</span>';
    }
    return '<span class="badge badge-healthy"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="11" height="11"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/></svg> Next lot</span>';
  }

  function wireRedeemFuel() {
    var form = qs("[data-redeem-form]");
    if (!form) return;
    var lotsEl = qs("#user-lots-data");
    if (lotsEl) {
      try { USER_LOTS = JSON.parse(lotsEl.textContent); } catch (e) {}
    }
    var available = parseFloat(form.getAttribute("data-available-litres"));
    var litresInput = qs("[data-redeem-litres-input]", form);
    var errorEl = qs("[data-redeem-error]", form);
    var breakdownEl = qs("[data-lot-breakdown]", form);
    var submitBtn = qs('button[type="submit"]', form);

    function renderBreakdown() {
      var target = parseFloat(litresInput.value) || 0;
      var over = target > available;
      errorEl.style.display = over ? "block" : "none";
      litresInput.setCustomValidity(over ? "Exceeds available balance" : "");
      if (submitBtn) submitBtn.disabled = over || target <= 0;

      var remaining = Math.min(target, available);
      var rows = [];
      for (var i = 0; i < USER_LOTS.length && remaining > 0.0001; i++) {
        var lot = USER_LOTS[i];
        var draw = Math.min(lot.litres, remaining);
        if (draw <= 0) continue;
        rows.push(
          '<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0">' +
          '<div><div style="font-weight:600;font-size:13.5px">' + fmtLitres(draw, 3) + 'L</div>' +
          '<div class="txn-sub">' + lot.label + '</div></div>' +
          badgeHtml(lot.badge) + '</div>'
        );
        remaining -= draw;
      }
      breakdownEl.innerHTML = rows.length
        ? rows.join('<div class="divider" style="margin:6px 0"></div>')
        : '<p style="text-align:center;padding:14px 0;color:var(--ink-faint);font-size:13px">Enter how many litres to see which lots will be used.</p>';
    }

    litresInput.addEventListener("input", renderBreakdown);
    renderBreakdown();

    qsa("[data-station-card] input[type=radio]", form).forEach(function (radio) {
      radio.addEventListener("change", function () {
        qsa("[data-station-card]", form).forEach(function (card) {
          var checked = qs("input[type=radio]", card).checked;
          card.classList.toggle("selected", checked);
          var check = qs(".station-check", card);
          if (check) check.style.visibility = checked ? "visible" : "hidden";
        });
      });
    });
  }

  function stashRedemption(form) {
    var litres = parseFloat(qs("[data-redeem-litres-input]", form).value) || 0;
    var checkedRadio = qs('input[name="station"]:checked', form);
    var stationLabel = "Total Lekki Phase 1";
    if (checkedRadio) {
      var card = checkedRadio.closest("[data-station-card]");
      var nameEl = card && qs(".station-name", card);
      if (nameEl) stationLabel = nameEl.textContent;
    }
    stash("redemption", {
      litres: litres,
      station: stationLabel,
      code: String(Math.floor(100000 + Math.random() * 899999))
    });
  }

  /* ==========================================================================
     10. QR Redemption screen — countdown + reflect stashed redemption
     ========================================================================== */
  function wireQrScreen() {
    var screen = qs("[data-qr-screen]");
    if (!screen) return;

    var redemption = unstash("redemption");
    if (redemption) {
      var litresEl = qs("[data-redemption-litres]", screen);
      var stationEl = qs("[data-redemption-station]", screen);
      if (litresEl) litresEl.childNodes[0].textContent = fmtLitres(redemption.litres, 3);
      if (stationEl) stationEl.textContent = redemption.station;
    }

    var seconds = parseInt(screen.getAttribute("data-countdown-seconds"), 10) || 600;
    var display = qs("[data-countdown-display]", screen);
    var expiredRedirect = screen.getAttribute("data-expired-redirect");
    var timer = setInterval(function () {
      seconds -= 1;
      var m = Math.floor(seconds / 60), s = seconds % 60;
      if (display) display.textContent = m + ":" + (s < 10 ? "0" : "") + s;
      if (seconds <= 0) {
        clearInterval(timer);
        if (expiredRedirect) window.location.href = expiredRedirect;
      }
    }, 1000);

    var cancelBtn = qs("[data-cancel-redemption]", screen.closest("body") || document);
    if (cancelBtn) {
      cancelBtn.addEventListener("click", function (e) {
        e.preventDefault();
        clearInterval(timer);
        window.location.href = cancelBtn.getAttribute("data-redirect");
      });
    }
  }

  /* ==========================================================================
     11. Attendant portal — scan simulation + code-entry toggle
     ========================================================================== */
  function wireAttendantPortal() {
    var scanBtn = qs("[data-scan-qr]");
    if (scanBtn) {
      scanBtn.addEventListener("click", function () {
        var label = qs("[data-scan-label]", scanBtn);
        scanBtn.disabled = true;
        if (label) label.textContent = "Scanning…";
        setTimeout(function () {
          window.location.href = scanBtn.getAttribute("data-scan-redirect");
        }, 900);
      });
    }
    var toggleBtn = qs("[data-toggle-code-entry]");
    var codeForm = qs("[data-code-entry-form]");
    if (toggleBtn && codeForm) {
      toggleBtn.addEventListener("click", function () {
        var willShow = codeForm.hasAttribute("hidden");
        if (willShow) { codeForm.removeAttribute("hidden"); qs("input", codeForm).focus(); }
        else { codeForm.setAttribute("hidden", ""); }
      });
    }
  }

  /* ==========================================================================
     12. Price History — tab switching redraws the SVG line chart
     ========================================================================== */
  function buildChartSvg(points) {
    var width = 350, height = 170;
    var vals = points.map(function (p) { return p[1]; });
    var vmin = Math.min.apply(null, vals), vmax = Math.max.apply(null, vals);
    var pad = (vmax - vmin) * 0.25 || 50;
    vmin -= pad; vmax += pad;
    var n = points.length;
    var xs = points.map(function (_, i) { return (i / (n - 1)) * (width - 20) + 10; });
    var ys = points.map(function (p) { return height - 24 - ((p[1] - vmin) / (vmax - vmin)) * (height - 50); });
    var path = "M " + xs.map(function (x, i) { return x.toFixed(1) + "," + ys[i].toFixed(1); }).join(" L ");
    var area = path + " L " + xs[n - 1].toFixed(1) + "," + (height - 10) + " L " + xs[0].toFixed(1) + "," + (height - 10) + " Z";
    var dots = xs.map(function (x, i) {
      return '<circle cx="' + x.toFixed(1) + '" cy="' + ys[i].toFixed(1) + '" r="3.2" fill="#116B42"/>';
    }).join("");
    var last = '<circle cx="' + xs[n - 1].toFixed(1) + '" cy="' + ys[n - 1].toFixed(1) + '" r="5" fill="#116B42" stroke="#fff" stroke-width="2"/>';
    var labels = xs.map(function (x, i) {
      return '<text x="' + x.toFixed(1) + '" y="' + (height - 2) + '" font-size="9.5" fill="#7D8C85" text-anchor="middle" font-family="IBM Plex Mono">' + points[i][0] + '</text>';
    }).join("");
    var grid = [0, 1, 2, 3].map(function (i) {
      var y = (height - 24 - i * (height - 50) / 3).toFixed(1);
      return '<line x1="10" y1="' + y + '" x2="' + (width - 10) + '" y2="' + y + '" stroke="#EDEEE8" stroke-width="1"/>';
    }).join("");
    return grid + '<path d="' + area + '" fill="#116B42" opacity="0.08"/>' +
      '<path d="' + path + '" fill="none" stroke="#116B42" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>' +
      dots + last + labels;
  }

  function wirePriceHistoryTabs() {
    var tabsWrap = qs("[data-price-tabs]");
    var dataEl = qs("#price-history-data");
    if (!tabsWrap || !dataEl) return;
    var datasets = JSON.parse(dataEl.textContent);
    var svg = qs("[data-price-chart-svg]");
    var tagEl = qs("[data-price-change-tag]");
    var textEl = qs("[data-price-change-text]");
    var rangeLabels = { "7D": "7 days", "30D": "30 days", "90D": "90 days", "1Y": "1 year" };

    function render(range) {
      var points = datasets[range];
      svg.innerHTML = buildChartSvg(points);
      var first = points[0][1], last = points[points.length - 1][1];
      var pct = ((last - first) / first) * 100;
      var up = pct > 0.05, down = pct < -0.05;
      tagEl.className = "tag " + (up ? "tag-up" : down ? "tag-down" : "tag-flat");
      var arrow = up
        ? '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="12" height="12"><path d="M7 17 17 7M9 7h8v8"/></svg> '
        : down
        ? '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="12" height="12"><path d="M7 7 17 17M17 9v8H9"/></svg> '
        : '';
      tagEl.innerHTML = arrow + '<span data-price-change-text>' + (pct >= 0 ? "+" : "") + pct.toFixed(1) + "% in " + rangeLabels[range] + '</span>';
    }

    qsa(".pill-tab[data-range]", tabsWrap).forEach(function (tab) {
      tab.addEventListener("click", function () {
        qsa(".pill-tab", tabsWrap).forEach(function (t) { t.classList.remove("active"); });
        tab.classList.add("active");
        render(tab.getAttribute("data-range"));
      });
    });

    var activeTab = qs(".pill-tab.active[data-range]", tabsWrap);
    if (activeTab) render(activeTab.getAttribute("data-range"));
  }

  /* ==========================================================================
     13. Transaction History — filter tabs
     ========================================================================== */
  function wireTxnTabs() {
    var tabsWrap = qs("[data-txn-tabs]");
    var list = qs("[data-txn-list]");
    if (!tabsWrap || !list) return;
    var rows = qsa(".txn[data-txn-type]", list);
    var empty = qs("[data-txn-empty]", list);

    function apply(filter) {
      var visibleCount = 0;
      rows.forEach(function (row) {
        var match = filter === "all" || row.getAttribute("data-txn-type") === filter;
        row.style.display = match ? "" : "none";
        if (match) visibleCount++;
      });
      if (empty) empty.hidden = visibleCount > 0;
    }

    qsa(".pill-tab[data-filter]", tabsWrap).forEach(function (tab) {
      tab.addEventListener("click", function () {
        qsa(".pill-tab", tabsWrap).forEach(function (t) { t.classList.remove("active"); });
        tab.classList.add("active");
        apply(tab.getAttribute("data-filter"));
      });
    });
  }

  /* ==========================================================================
     14. Admin: inline "saved" confirmation for forms with no page to go to
     ========================================================================== */
  function wireAdminInlineForms() {
    qsa("form[data-price-form], #validity-days").forEach(function () {}); // no-op guard
    var priceForm = qs("[data-price-form]");
    if (priceForm) {
      priceForm.addEventListener("submit", function (e) {
        e.preventDefault();
        showInlineSuccess(priceForm, "New price scheduled. It will take effect at the time you set.");
      });
    }
    var validityForm = qs('form[action="/admin/litre-validity/update/"]');
    if (validityForm) {
      validityForm.addEventListener("submit", function (e) {
        e.preventDefault();
        showInlineSuccess(validityForm, "Default litre validity updated for future purchases.");
      });
    }
  }

  function showInlineSuccess(form, message) {
    var existing = qs("[data-inline-success]", form);
    if (existing) existing.remove();
    var div = document.createElement("div");
    div.className = "notice notice-green";
    div.setAttribute("data-inline-success", "");
    div.style.marginTop = "14px";
    div.innerHTML = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="16" height="16"><circle cx="12" cy="12" r="9"/><path d="M8.5 12.5l2.3 2.3L16 9.7"/></svg><div>' + message + '</div>';
    form.appendChild(div);
    setTimeout(function () { div.remove(); }, 4000);
  }

  /* ==========================================================================
     15. Admin Stations — add/edit/delete (client-side demo of a CRUD table)
     ========================================================================== */
  function wireAdminStations() {
    var form = qs("[data-station-form]");
    var table = qs("[data-stations-table]");
    if (!form || !table) return;
    var tbody = qs("tbody", table);
    var nameField = qs("#station-name", form);
    var addressField = qs("#station-address", form);
    var codeField = qs("#station-code", form);
    var activeField = qs('input[name="active"]', form);
    var idField = qs("[data-station-id-field]", form);

    function resetForm() {
      form.reset();
      idField.value = "";
    }

    qsa("[data-toggle-station-form]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var isHidden = form.hasAttribute("hidden");
        if (isHidden) {
          resetForm();
          form.removeAttribute("hidden");
          nameField.focus();
          form.scrollIntoView({ behavior: "smooth", block: "center" });
        } else {
          form.setAttribute("hidden", "");
        }
      });
    });

    qsa("[data-edit-station]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var row = btn.closest("[data-station-row]");
        nameField.value = row.getAttribute("data-name");
        addressField.value = row.getAttribute("data-address");
        codeField.value = row.getAttribute("data-code");
        activeField.checked = row.getAttribute("data-active") === "true";
        idField.value = row.getAttribute("data-code");
        form.removeAttribute("hidden");
        nameField.focus();
        form.scrollIntoView({ behavior: "smooth", block: "center" });
      });
    });

    qsa("[data-delete-station]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var row = btn.closest("[data-station-row]");
        var name = row.getAttribute("data-name");
        if (window.confirm('Remove "' + name + '" from the station network?')) {
          row.remove();
        }
      });
    });

    function statusCellHtml(active) {
      return active ? '<span class="tag tag-down">Active</span>' : '<span class="tag tag-flat">Inactive</span>';
    }
    function actionsCellHtml() {
      return '<button type="button" class="icon-btn" data-edit-station style="display:inline-flex"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="15" height="15"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg></button> ' +
        '<button type="button" class="icon-btn" data-delete-station style="display:inline-flex"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="15" height="15"><path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2m-9 0 1 13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1l1-13"/></svg></button>';
    }
    function bindRowButtons(row) {
      qs("[data-edit-station]", row).addEventListener("click", function () {
        nameField.value = row.getAttribute("data-name");
        addressField.value = row.getAttribute("data-address");
        codeField.value = row.getAttribute("data-code");
        activeField.checked = row.getAttribute("data-active") === "true";
        idField.value = row.getAttribute("data-code");
        form.removeAttribute("hidden");
        nameField.focus();
        form.scrollIntoView({ behavior: "smooth", block: "center" });
      });
      qs("[data-delete-station]", row).addEventListener("click", function () {
        if (window.confirm('Remove "' + row.getAttribute("data-name") + '" from the station network?')) {
          row.remove();
        }
      });
    }

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (!form.checkValidity()) { form.reportValidity(); return; }
      var data = {
        name: nameField.value.trim(),
        address: addressField.value.trim(),
        code: codeField.value.trim(),
        active: activeField.checked
      };
      var editingCode = idField.value;
      var existingRow = editingCode ? qs('[data-station-row][data-code="' + CSS.escape(editingCode) + '"]', tbody) : null;

      if (existingRow) {
        existingRow.setAttribute("data-name", data.name);
        existingRow.setAttribute("data-address", data.address);
        existingRow.setAttribute("data-code", data.code);
        existingRow.setAttribute("data-active", data.active ? "true" : "false");
        existingRow.children[0].textContent = data.name;
        existingRow.children[1].textContent = data.address;
        existingRow.children[2].textContent = data.code;
        existingRow.children[3].innerHTML = statusCellHtml(data.active);
      } else {
        var tr = document.createElement("tr");
        tr.setAttribute("data-station-row", "");
        tr.setAttribute("data-name", data.name);
        tr.setAttribute("data-address", data.address);
        tr.setAttribute("data-code", data.code);
        tr.setAttribute("data-active", data.active ? "true" : "false");
        tr.innerHTML =
          '<td style="font-weight:600">' + data.name + '</td>' +
          '<td>' + data.address + '</td>' +
          '<td class="mono">' + data.code + '</td>' +
          '<td>' + statusCellHtml(data.active) + '</td>' +
          '<td style="text-align:right">' + actionsCellHtml() + '</td>';
        tbody.appendChild(tr);
        bindRowButtons(tr);
      }
      form.setAttribute("hidden", "");
      resetForm();
    });

    qsa("[data-station-row]", tbody).forEach(bindRowButtons);
  }

  /* ==========================================================================
     16. Password strength indicator (reset-password screen)
     ========================================================================== */
  function wirePasswordStrength() {
    var input = qs("[data-strength-input]");
    var notice = qs("[data-strength-notice]");
    var text = qs("[data-strength-text]");
    if (!input || !notice || !text) return;

    function score(pw) {
      var s = 0;
      if (pw.length >= 8) s++;
      if (pw.length >= 12) s++;
      if (/[0-9]/.test(pw)) s++;
      if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) s++;
      if (/[^A-Za-z0-9]/.test(pw)) s++;
      return s;
    }

    input.addEventListener("input", function () {
      var pw = input.value;
      if (!pw) {
        notice.className = "notice notice-green";
        text.textContent = "Enter a password to check its strength.";
        return;
      }
      var s = score(pw);
      if (s <= 2) {
        notice.className = "notice notice-red";
        text.textContent = "Weak — try adding a number, a symbol, or more characters.";
      } else if (s <= 3) {
        notice.className = "notice notice-amber";
        text.textContent = "Okay — a longer password with a symbol would be stronger.";
      } else {
        notice.className = "notice notice-green";
        text.textContent = "Great password strength.";
      }
    });
  }

  /* ---------- boot ---------- */
  document.addEventListener("DOMContentLoaded", function () {
    wireDemoForms();
    wirePasswordToggles();
    wirePhoneLogin();
    wireOtp();
    wireResend();
    wireBuyLitres();
    wireProcessingScreen();
    wirePurchaseSuccess();
    wireRedeemFuel();
    wireQrScreen();
    wireAttendantPortal();
    wirePriceHistoryTabs();
    wireTxnTabs();
    wireAdminInlineForms();
    wireAdminStations();
    wirePasswordStrength();
  });
})();
