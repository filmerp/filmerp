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

    const floatingTooltip = document.createElement("div");
    floatingTooltip.id = "sidebar-floating-tooltip";
    floatingTooltip.className = "sidebar-floating-tooltip";
    floatingTooltip.setAttribute("role", "tooltip");
    document.body.append(floatingTooltip);
    let tooltipTarget = null;

    function hideFloatingTooltip() {
      tooltipTarget = null;
      floatingTooltip.classList.remove("is-visible");
    }

    function showFloatingTooltip(target) {
      const label = target.dataset.tooltip;
      if (!desktop.matches || !collapsed || !label) {
        hideFloatingTooltip();
        return;
      }

      const rect = target.getBoundingClientRect();
      tooltipTarget = target;
      floatingTooltip.textContent = label;
      floatingTooltip.style.left = Math.round(rect.right + 10) + "px";
      floatingTooltip.style.top = Math.round(rect.top + rect.height / 2) + "px";
      floatingTooltip.classList.add("is-visible");
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
      hideFloatingTooltip();
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
        desktopToggle.focus({ preventScroll: true });
      }
    });

    overlay.addEventListener("click", function () {
      closeMobileMenu(true);
    });

    sidebar.querySelectorAll(".sidebar-link").forEach(function (link) {
      if (link.dataset.tooltip) {
        link.setAttribute("aria-label", link.dataset.tooltip);
      }
      link.addEventListener("mouseenter", function () {
        showFloatingTooltip(link);
      });
      link.addEventListener("mouseleave", function () {
        if (tooltipTarget === link) {
          hideFloatingTooltip();
        }
      });
      link.addEventListener("focus", function () {
        showFloatingTooltip(link);
      });
      link.addEventListener("blur", function () {
        if (tooltipTarget === link) {
          hideFloatingTooltip();
        }
      });
      link.addEventListener("click", function () {
        if (link.tagName === "SUMMARY") {
          return;
        }
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

    const sidebarNav = sidebar.querySelector(".sidebar-nav");
    if (sidebarNav) {
      sidebarNav.addEventListener("scroll", hideFloatingTooltip, { passive: true });
    }
    window.addEventListener("resize", hideFloatingTooltip, { passive: true });

    if (desktop.addEventListener) {
      desktop.addEventListener("change", applyLayout);
    } else {
      desktop.addListener(applyLayout);
    }

    applyLayout();
  }

  function initializeIdleLogout() {
    const sidebar = document.getElementById("app-sidebar");
    const logoutForm = sidebar ? sidebar.querySelector(".sidebar-logout-form") : null;

    if (!sidebar || !logoutForm || sidebar.dataset.idleReady === "true") {
      return;
    }
    sidebar.dataset.idleReady = "true";

    const timeoutMs = Number.parseInt(sidebar.dataset.idleTimeoutMs, 10) || 600000;
    const warningMs = Number.parseInt(sidebar.dataset.idleWarningMs, 10) || 60000;
    const keepaliveUrl = sidebar.dataset.keepaliveUrl;
    const userKey = sidebar.dataset.sessionUser || "authenticated";
    const activityKey = "filmerp-session-activity-" + userKey;
    const keepaliveKey = "filmerp-session-keepalive-" + userKey;
    const csrfInput = logoutForm.querySelector("input[name='csrfmiddlewaretoken']");
    let lastLocalActivity = Date.now();
    let logoutStarted = false;

    const warning = document.createElement("section");
    warning.className = "session-timeout-warning";
    warning.hidden = true;
    warning.setAttribute("role", "alertdialog");
    warning.setAttribute("aria-labelledby", "session-timeout-title");
    warning.setAttribute("aria-describedby", "session-timeout-message");

    const warningCopy = document.createElement("div");
    const warningTitle = document.createElement("strong");
    warningTitle.id = "session-timeout-title";
    warningTitle.textContent = "Sesja wkrótce wygaśnie";
    const warningMessage = document.createElement("span");
    warningMessage.id = "session-timeout-message";
    warningCopy.append(warningTitle, warningMessage);

    const stayButton = document.createElement("button");
    stayButton.type = "button";
    stayButton.textContent = "Pozostań zalogowany";
    warning.append(warningCopy, stayButton);
    document.body.append(warning);

    function readStoredNumber(key) {
      try {
        return Number.parseInt(window.localStorage.getItem(key), 10) || 0;
      } catch (error) {
        return 0;
      }
    }

    function writeStoredNumber(key, value) {
      try {
        window.localStorage.setItem(key, String(value));
      } catch (error) {
        // Session expiry still works in the current tab without local storage.
      }
    }

    function hideWarning() {
      warning.hidden = true;
    }

    function refreshServerSession(now, force) {
      if (!keepaliveUrl || !csrfInput) {
        return;
      }

      const lastKeepalive = readStoredNumber(keepaliveKey);
      if (!force && now - lastKeepalive < 60000) {
        return;
      }
      writeStoredNumber(keepaliveKey, now);

      window.fetch(keepaliveUrl, {
        method: "POST",
        credentials: "same-origin",
        keepalive: true,
        headers: {
          "X-CSRFToken": csrfInput.value,
          "X-Requested-With": "XMLHttpRequest"
        }
      }).then(function (response) {
        if (response.redirected || !response.ok) {
          submitLogout();
        }
      }).catch(function () {
        // The next protected request will enforce the server-side session state.
      });
    }

    function recordActivity(forceKeepalive) {
      const now = Date.now();
      if (!forceKeepalive && now - lastLocalActivity < 5000) {
        return;
      }

      lastLocalActivity = now;
      writeStoredNumber(activityKey, now);
      hideWarning();
      refreshServerSession(now, forceKeepalive);
    }

    function submitLogout() {
      if (logoutStarted) {
        return;
      }
      logoutStarted = true;
      const reasonInput = logoutForm.querySelector("input[name='logout_reason']");
      if (reasonInput) {
        reasonInput.value = "idle";
      }
      try {
        window.localStorage.removeItem(activityKey);
        window.localStorage.removeItem(keepaliveKey);
      } catch (error) {
        // Storage cleanup is optional.
      }

      if (typeof logoutForm.requestSubmit === "function") {
        logoutForm.requestSubmit();
      } else {
        logoutForm.submit();
      }
    }

    function checkInactivity() {
      const now = Date.now();
      const storedActivity = Math.min(readStoredNumber(activityKey), now);
      const lastActivity = Math.max(lastLocalActivity, storedActivity);
      const idleMs = now - lastActivity;
      const remainingMs = timeoutMs - idleMs;

      if (remainingMs <= 0) {
        submitLogout();
        return;
      }

      if (remainingMs <= warningMs) {
        warningMessage.textContent = "Automatyczne wylogowanie za " + Math.max(1, Math.ceil(remainingMs / 1000)) + " s.";
        warning.hidden = false;
      } else {
        hideWarning();
      }
    }

    stayButton.addEventListener("click", function () {
      recordActivity(true);
    });

    document.addEventListener("pointerdown", function () {
      recordActivity(false);
    }, { passive: true });
    document.addEventListener("touchstart", function () {
      recordActivity(false);
    }, { passive: true });
    document.addEventListener("keydown", function () {
      recordActivity(false);
    });
    document.addEventListener("input", function () {
      recordActivity(false);
    });
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "visible") {
        checkInactivity();
        if (!logoutStarted) {
          recordActivity(true);
        }
      }
    });
    window.addEventListener("storage", function (event) {
      if (event.key === activityKey) {
        hideWarning();
        checkInactivity();
      }
    });

    const now = Date.now();
    lastLocalActivity = now;
    writeStoredNumber(activityKey, now);
    writeStoredNumber(keepaliveKey, now);
    window.setInterval(checkInactivity, 1000);
  }

  function initialize() {
    initializeSidebar();
    initializeIdleLogout();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize, { once: true });
  } else {
    initialize();
  }
})();
