(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    const addButton = document.getElementById("add-budget-line");
    const lines = document.getElementById("pa-budget-lines");
    const template = document.getElementById("empty-budget-line-template");
    const totalForms = document.getElementById("id_lines-TOTAL_FORMS");
    if (!addButton || !lines || !template || !totalForms) return;

    addButton.addEventListener("click", function () {
      const index = Number(totalForms.value);
      const wrapper = document.createElement("div");
      wrapper.innerHTML = template.innerHTML.replaceAll("__prefix__", String(index)).trim();
      const line = wrapper.firstElementChild;
      if (!line) return;
      lines.appendChild(line);
      totalForms.value = String(index + 1);
      document.dispatchEvent(new CustomEvent("filmerp:cost-scope-added", {
        detail: {container: line.querySelector("[data-cost-scope-container]")},
      }));
      const nameField = line.querySelector('input[name$="-name"]');
      if (nameField) nameField.focus();
    });

    if (Number(totalForms.value) === 0) addButton.click();
  });
})();
