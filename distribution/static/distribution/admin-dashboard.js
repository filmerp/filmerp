(function () {
  function initializeAdminHub() {
    const hub = document.querySelector("[data-admin-hub]");
    if (!hub) return;

    const tabs = Array.from(hub.querySelectorAll("[data-admin-tab]"));
    const panels = Array.from(hub.querySelectorAll("[data-admin-panel]"));
    if (!tabs.length || !panels.length) return;

    function activate(appLabel, moveFocus) {
      const selected = tabs.find((tab) => tab.dataset.adminTab === appLabel) || tabs[0];
      tabs.forEach((tab) => {
        const active = tab === selected;
        tab.classList.toggle("is-active", active);
        tab.setAttribute("aria-selected", String(active));
        tab.tabIndex = active ? 0 : -1;
      });
      panels.forEach((panel) => {
        panel.hidden = panel.dataset.adminPanel !== selected.dataset.adminTab;
      });
      if (moveFocus) selected.focus();
      if (window.history && window.history.replaceState) {
        window.history.replaceState(null, "", `#admin-${selected.dataset.adminTab}`);
      }
    }

    tabs.forEach((tab, index) => {
      tab.addEventListener("click", () => activate(tab.dataset.adminTab, false));
      tab.addEventListener("keydown", (event) => {
        let targetIndex = null;
        if (event.key === "ArrowRight") targetIndex = (index + 1) % tabs.length;
        if (event.key === "ArrowLeft") targetIndex = (index - 1 + tabs.length) % tabs.length;
        if (event.key === "Home") targetIndex = 0;
        if (event.key === "End") targetIndex = tabs.length - 1;
        if (targetIndex === null) return;
        event.preventDefault();
        activate(tabs[targetIndex].dataset.adminTab, true);
      });
    });

    const requested = window.location.hash.replace("#admin-", "");
    const initial = tabs.some((tab) => tab.dataset.adminTab === requested)
      ? requested
      : (tabs.find((tab) => tab.dataset.adminTab === "distribution") || tabs[0]).dataset.adminTab;
    activate(initial, false);
  }

  document.addEventListener("DOMContentLoaded", initializeAdminHub);
})();
