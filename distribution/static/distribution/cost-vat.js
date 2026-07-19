(function () {
  "use strict";

  function parseAmount(value) {
    const normalized = String(value || "").replace(/\s/g, "").replace(",", ".");
    const parsed = Number.parseFloat(normalized);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function formatAmount(value) {
    return value.toLocaleString("pl-PL", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function initializeVatCalculations(root) {
    (root || document).querySelectorAll('input[name$="net_amount"]').forEach(function (netInput) {
      const rateName = netInput.name.replace(/net_amount$/, "vat_rate");
      const form = netInput.closest("form") || document;
      const rateInput = form.querySelector('[name="' + rateName + '"]');
      if (!rateInput || rateInput.dataset.vatReady === "true") return;
      rateInput.dataset.vatReady = "true";

      const mainForm = rateInput.name === "vat_rate";
      const vatReadonly = mainForm ? form.querySelector(".field-vat_amount_display .readonly") : null;
      const grossReadonly = mainForm ? form.querySelector(".field-gross_amount_display .readonly") : null;
      let preview = null;

      if (!vatReadonly || !grossReadonly) {
        preview = document.createElement("span");
        preview.className = "vat-live-preview";
        rateInput.insertAdjacentElement("afterend", preview);
      }

      function update() {
        const net = parseAmount(netInput.value);
        const rate = parseAmount(rateInput.value);
        const rawVat = net * rate / 100;
        const vat = Math.round((rawVat + Number.EPSILON) * 100) / 100;
        const gross = net + vat;

        if (vatReadonly) vatReadonly.textContent = formatAmount(vat);
        if (grossReadonly) grossReadonly.textContent = formatAmount(gross);
        if (preview) preview.textContent = "Kwota VAT: " + formatAmount(vat) + " · Brutto (VAT): " + formatAmount(gross);
      }

      netInput.addEventListener("input", update);
      rateInput.addEventListener("input", update);
      update();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      initializeVatCalculations();
    }, { once: true });
  } else {
    initializeVatCalculations();
  }
  document.addEventListener("formset:added", function (event) {
    initializeVatCalculations(event.target);
  });
})();
