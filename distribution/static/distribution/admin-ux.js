(function () {
  "use strict";

  const scrollStorageKey = "filmerp-admin-return-scroll";

  function sameOrigin(url) {
    try {
      return new URL(url, window.location.href).origin === window.location.origin;
    } catch (error) {
      return false;
    }
  }

  function scrollIdentity(value) {
    const url = new URL(value, window.location.href);
    url.searchParams.delete("return_to");
    return url.href;
  }

  function rememberScroll() {
    try {
      window.sessionStorage.setItem(scrollStorageKey, JSON.stringify({
        url: scrollIdentity(window.location.href),
        y: window.scrollY,
      }));
    } catch (error) {
      // Navigation remains functional when storage is unavailable.
    }
  }

  function restoreScroll() {
    try {
      const saved = JSON.parse(window.sessionStorage.getItem(scrollStorageKey) || "null");
      if (saved && saved.url === scrollIdentity(window.location.href)) {
        window.scrollTo({ top: saved.y, behavior: "auto" });
        window.sessionStorage.removeItem(scrollStorageKey);
      }
    } catch (error) {
      window.sessionStorage.removeItem(scrollStorageKey);
    }
  }

  function relatedObjectUrl(link) {
    const relationFieldId = link.id.replace(/^(change|view)_/, "");
    const relationField = document.getElementById(relationFieldId);
    const selectedValue = relationField ? relationField.value : "";
    let rawUrl = link.getAttribute("href") || link.dataset.hrefTemplate || "";

    if (!rawUrl || rawUrl === "#" || (rawUrl.includes("__fk__") && !selectedValue)) return null;
    rawUrl = rawUrl.replace("__fk__", encodeURIComponent(selectedValue));
    const target = new URL(rawUrl, window.location.href);
    const current = new URL(window.location.href);
    const parentReturn = document.querySelector('#content-main form input[name="return_to"]')?.value;
    if (parentReturn && !current.searchParams.has("return_to")) {
      current.searchParams.set("return_to", parentReturn);
    }
    target.searchParams.delete("_popup");
    target.searchParams.set("return_to", current.href);
    return target.href;
  }

  function simplifyAdminLanguage() {
    const replacements = [
      ["Dodaj kolejne(go)(-ną)(-ny)", "Dodaj pozycję"],
      ["Zmień wybraną(-ne)(-nego)(-ny)", "Edytuj wybrane pozycje"],
      ["Usuń wybraną(-ne)(-nego)(-ny)", "Usuń wybrane pozycje"],
      ["Obejrzyj wybraną(-ne)(-nego)(-ny)", "Wyświetl wybraną pozycję"],
    ];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
      if (!node.parentElement.closest("script, style, textarea")) {
        replacements.forEach(function (replacement) {
          node.nodeValue = node.nodeValue.replaceAll(replacement[0], replacement[1]);
        });
      }
      node = walker.nextNode();
    }

    document.querySelectorAll(".add-row a, .add-row button").forEach(function (control) {
      if (control.dataset.filmerpSimplified === "true") return;
      control.dataset.filmerpSimplified = "true";
      Array.from(control.childNodes).forEach(function (node) {
        if (node.nodeType === Node.TEXT_NODE) node.remove();
      });
      control.append(document.createTextNode(" Dodaj pozycję"));
      control.setAttribute("aria-label", "Dodaj pozycję");
    });

    const relatedLabels = {
      "add-related": "Dodaj",
      "change-related": "Edytuj",
      "delete-related": "Usuń",
      "view-related": "Podgląd",
    };
    document.querySelectorAll(".related-widget-wrapper-link").forEach(function (link) {
      Object.entries(relatedLabels).forEach(function (entry) {
        if (!link.classList.contains(entry[0])) return;
        link.title = entry[1];
        link.setAttribute("aria-label", entry[1]);
        const image = link.querySelector("img");
        if (image) image.alt = entry[1];
      });
    });

    document.querySelectorAll('select[name="action"] option').forEach(function (option) {
      if (option.textContent.trim().startsWith("Usuń wybran")) option.textContent = "Usuń wybrane pozycje";
    });
  }

  function initializeRelatedNavigation() {
    document.querySelectorAll(".change-related, .view-related").forEach(function (link) {
      link.removeAttribute("target");
      link.removeAttribute("data-popup");
      link.addEventListener("click", function (event) {
        const targetUrl = relatedObjectUrl(link);
        if (!targetUrl) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        rememberScroll();
        window.location.assign(targetUrl);
      }, true);
    });
  }

  function initializeCancelButton() {
    if (!document.body.classList.contains("change-form")) return;
    const form = document.querySelector("#content-main form[method='post']");
    if (!form) return;

    let returnInput = form.querySelector('input[name="return_to"]');
    const queryReturn = new URLSearchParams(window.location.search).get("return_to");
    const referrerReturn = sameOrigin(document.referrer) ? document.referrer : "";
    const breadcrumbLinks = Array.from(document.querySelectorAll("div.breadcrumbs a"));
    const fallback = breadcrumbLinks.length ? breadcrumbLinks[breadcrumbLinks.length - 1].href : "/admin/";
    const returnUrl = (returnInput && returnInput.value) || queryReturn || referrerReturn || fallback;

    if (!returnInput) {
      returnInput = document.createElement("input");
      returnInput.type = "hidden";
      returnInput.name = "return_to";
      form.appendChild(returnInput);
    }
    returnInput.value = returnUrl;

    document.querySelectorAll(".submit-row").forEach(function (row) {
      if (row.querySelector(".filmerp-cancel-link")) return;
      const cancel = document.createElement("a");
      cancel.className = "button filmerp-cancel-link";
      cancel.href = returnUrl;
      cancel.textContent = "Anuluj";
      cancel.addEventListener("click", rememberScroll);
      row.appendChild(cancel);
    });
  }

  function initializeAdminUx() {
    restoreScroll();
    simplifyAdminLanguage();
    initializeRelatedNavigation();
    initializeCancelButton();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeAdminUx, { once: true });
  } else {
    initializeAdminUx();
  }
  window.addEventListener("load", simplifyAdminLanguage, { once: true });
})();
