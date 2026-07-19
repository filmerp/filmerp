(function () {
  "use strict";

  function initializeSidebar() {
    const body = document.body;
    const sidebar = document.getElementById("app-sidebar");
    const desktopToggle = document.getElementById("sidebar-toggle");
    const mobileToggle = document.getElementById("mobile-menu-toggle");
    const overlay = document.getElementById("sidebar-overlay");

    if (!sidebar || !desktopToggle || !mobileToggle || !overlay || sidebar.dataset.ready === "true") {
      return;
    }
    sidebar.dataset.ready = "true";

    const desktop = window.matchMedia("(min-width: 961px)");
    const storageKey = "filmerp-sidebar-collapsed";
    let collapsed = false;

    try {
      collapsed = window.localStorage.getItem(storageKey) === "1";
    } catch (error) {
      collapsed = false;
    }

    function mobileIsOpen() {
      return body.classList.contains("sidebar-mobile-open");
    }

    function updateControls() {
      const mobileOpen = mobileIsOpen();
      const sidebarHidden = !desktop.matches && !mobileOpen;

      desktopToggle.setAttribute("aria-expanded", String(desktop.matches ? !collapsed : mobileOpen));
      desktopToggle.setAttribute("aria-label", desktop.matches ? (collapsed ? "Rozwiń menu" : "Zwiń menu") : "Zamknij menu");
      desktopToggle.dataset.tooltip = collapsed ? "Rozwiń menu" : "Zwiń menu";
      mobileToggle.setAttribute("aria-expanded", String(mobileOpen));
      mobileToggle.setAttribute("aria-label", mobileOpen ? "Zamknij menu" : "Otwórz menu");
      sidebar.setAttribute("aria-hidden", String(sidebarHidden));

      if (sidebarHidden) {
        sidebar.setAttribute("inert", "");
      } else {
        sidebar.removeAttribute("inert");
      }
    }

    function closeMobileMenu(returnFocus) {
      body.classList.remove("sidebar-mobile-open");
      updateControls();
      if (returnFocus) {
        mobileToggle.focus();
      }
    }

    function applyLayout() {
      if (desktop.matches) {
        body.classList.remove("sidebar-mobile-open");
        body.classList.toggle("sidebar-collapsed", collapsed);
      } else {
        body.classList.remove("sidebar-collapsed");
      }
      updateControls();
    }

    desktopToggle.addEventListener("click", function () {
      if (!desktop.matches) {
        closeMobileMenu(true);
        return;
      }

      collapsed = !collapsed;
      try {
        window.localStorage.setItem(storageKey, collapsed ? "1" : "0");
      } catch (error) {
        // The layout still works when storage is unavailable.
      }
      applyLayout();
    });

    mobileToggle.addEventListener("click", function () {
      body.classList.toggle("sidebar-mobile-open");
      updateControls();
      if (mobileIsOpen()) {
        const firstLink = sidebar.querySelector(".sidebar-link");
        if (firstLink) {
          firstLink.focus({ preventScroll: true });
        }
      }
    });

    overlay.addEventListener("click", function () {
      closeMobileMenu(true);
    });

    sidebar.querySelectorAll(".sidebar-link").forEach(function (link) {
      link.addEventListener("click", function () {
        if (!desktop.matches) {
          closeMobileMenu(false);
        }
      });
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !desktop.matches && mobileIsOpen()) {
        closeMobileMenu(true);
      }
    });

    if (desktop.addEventListener) {
      desktop.addEventListener("change", applyLayout);
    } else {
      desktop.addListener(applyLayout);
    }

    applyLayout();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeSidebar, { once: true });
  } else {
    initializeSidebar();
  }
})();
