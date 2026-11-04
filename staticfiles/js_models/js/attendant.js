/*
 * Attendant portal: scan a customer's QR or type their 6-digit code, look
 * it up via the JSON API, then move on to the confirmation page.
 */
document.addEventListener("DOMContentLoaded", function () {
  const verifyUrl = document.body.dataset.verifyUrl;
  const verifyBaseUrl = document.body.dataset.verifyBaseUrl; // e.g. /attendant/verify/
  const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;

  function goToVerify(redemptionId) {
    window.location = verifyBaseUrl + redemptionId + "/";
  }

  function lookup(payload, errorEl) {
    const body = new URLSearchParams(payload);
    fetch(verifyUrl, {
      method: "POST",
      headers: {
        "X-CSRFToken": csrfToken,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body,
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.valid) {
          goToVerify(data.redemption_id);
        } else if (errorEl) {
          errorEl.textContent = "That code isn't valid or has expired. Try again.";
          errorEl.style.display = "block";
        }
      })
      .catch(() => {
        if (errorEl) {
          errorEl.textContent = "Something went wrong. Try again.";
          errorEl.style.display = "block";
        }
      });
  }

  // --- Manual code entry ---
  const codeForm = document.getElementById("code-form");
  if (codeForm) {
    codeForm.addEventListener("submit", function (e) {
      e.preventDefault();
      const code = document.getElementById("code-input").value.trim();
      const errorEl = document.getElementById("code-error");
      if (code.length === 6) {
        lookup({ code }, errorEl);
      }
    });
  }

  // --- QR scanning (only where the browser supports it) ---
  const scanBtn = document.getElementById("scan-btn");
  const scanPanel = document.getElementById("scan-panel");
  const video = document.getElementById("scan-video");
  const scanError = document.getElementById("scan-error");

  if (!scanBtn) return;

  if (!("BarcodeDetector" in window) || !navigator.mediaDevices) {
    scanBtn.disabled = true;
    scanBtn.title = "QR scanning isn't supported in this browser - use Enter Code instead.";
    return;
  }

  let scanning = false;

  scanBtn.addEventListener("click", async function () {
    scanPanel.style.display = "block";
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
      video.srcObject = stream;
      await video.play();
      scanning = true;
      const detector = new BarcodeDetector({ formats: ["qr_code"] });

      const scanLoop = async () => {
        if (!scanning) return;
        try {
          const codes = await detector.detect(video);
          if (codes.length > 0) {
            scanning = false;
            stream.getTracks().forEach((t) => t.stop());
            lookup({ qr_code: codes[0].rawValue }, scanError);
            return;
          }
        } catch (err) {
          /* keep trying */
        }
        requestAnimationFrame(scanLoop);
      };
      scanLoop();
    } catch (err) {
      scanError.textContent = "Camera access was denied - use Enter Code instead.";
      scanError.style.display = "block";
    }
  });
});
