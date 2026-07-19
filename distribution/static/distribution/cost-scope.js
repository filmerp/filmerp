(function () {
  "use strict";

  function closestRow(element) {
    return element && (element.closest(".form-row") || element.closest("label") || element.parentElement);
  }

  function setupScope(container) {
    const radios = Array.from(container.querySelectorAll('input[name$="scope_mode"]'));
    if (!radios.length) return;

    const prefix = radios[0].name.slice(0, -"scope_mode".length);
    const selectedField = container.querySelector(`[name="${prefix}scope_fields"]`);
    const selectedRow = container.querySelector("[data-cost-scope-selected]") || closestRow(selectedField);
    const allocationPanel = container.querySelector("[data-cost-scope-allocated]");
    const allocationRows = allocationPanel ? [allocationPanel] : Array.from(container.querySelectorAll(`[name^="${prefix}allocation_"]`))
      .filter((field) => field.name !== `${prefix}allocation_percentages`)
      .map(closestRow)
      .filter(Boolean);

    function update() {
      const checked = radios.find((radio) => radio.checked);
      const mode = checked ? checked.value : "all";
      if (selectedRow) selectedRow.hidden = mode !== "selected";
      allocationRows.forEach((row) => { row.hidden = mode !== "allocated"; });
    }

    radios.forEach((radio) => radio.addEventListener("change", update));
    update();
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("form").forEach(setupScope);
  });
})();
