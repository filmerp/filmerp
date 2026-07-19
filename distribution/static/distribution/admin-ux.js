(function () {
  "use strict";

  const scrollStorageKey = "filmerp-admin-return-scroll";
  const parentStatePrefix = "filmerp-admin-parent-";
  const helperParams = [
    "filmerp_restore",
    "filmerp_parent_key",
    "filmerp_parent_field",
    "filmerp_related_field",
    "filmerp_related_id",
    "filmerp_related_label",
  ];

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
    helperParams.forEach((name) => url.searchParams.delete(name));
    return url.href;
  }

  function rememberScroll() {
    try {
      window.sessionStorage.setItem(scrollStorageKey, JSON.stringify({
        url: scrollIdentity(window.location.href),
        y: window.scrollY,
      }));
    } catch (error) {
      // Nawigacja nadal działa, gdy pamięć sesji jest niedostępna.
    }
  }

  function restoreScroll() {
    try {
      const saved = JSON.parse(window.sessionStorage.getItem(scrollStorageKey) || "null");
      if (saved && saved.url === scrollIdentity(window.location.href)) {
        window.requestAnimationFrame(() => window.scrollTo({ top: saved.y, behavior: "auto" }));
        window.sessionStorage.removeItem(scrollStorageKey);
      }
    } catch (error) {
      window.sessionStorage.removeItem(scrollStorageKey);
    }
  }

  function snapshotParentForm(relationFieldId) {
    const form = document.querySelector("#content-main form[method='post']");
    if (!form) return "";

    const ordinals = {};
    const controls = [];
    Array.from(form.elements).forEach(function (control) {
      if (!control.name || control.name === "csrfmiddlewaretoken") return;
      if (["file", "submit", "button", "reset"].includes(control.type)) return;

      const ordinal = ordinals[control.name] || 0;
      ordinals[control.name] = ordinal + 1;
      const state = {
        name: control.name,
        ordinal: ordinal,
        tag: control.tagName,
        type: control.type,
      };
      if (control.tagName === "SELECT" && control.multiple) {
        state.values = Array.from(control.selectedOptions).map((option) => option.value);
      } else if (control.type === "checkbox" || control.type === "radio") {
        state.checked = control.checked;
        state.value = control.value;
      } else {
        state.value = control.value;
      }
      controls.push(state);
    });

    try {
      const key = `${parentStatePrefix}${Date.now()}-${Math.random().toString(36).slice(2)}`;
      window.sessionStorage.setItem(key, JSON.stringify({
        url: window.location.href,
        y: window.scrollY,
        relationFieldId: relationFieldId,
        controls: controls,
      }));
      return key;
    } catch (error) {
      return "";
    }
  }

  function relationNavigation(link) {
    const relationFieldId = link.id.replace(/^(add|change|view)_/, "");
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
    return { target: target, relationFieldId: relationFieldId };
  }

  function dispatchFieldChange(control) {
    control.dispatchEvent(new Event("input", { bubbles: true }));
    control.dispatchEvent(new Event("change", { bubbles: true }));
    if (window.django?.jQuery) {
      window.django.jQuery(control).trigger("change");
    }
  }

  function restoreParentFormState() {
    const params = new URLSearchParams(window.location.search);
    if (params.get("filmerp_restore") !== "1") return;

    const key = params.get("filmerp_parent_key");
    const form = document.querySelector("#content-main form[method='post']");
    if (!key || !form) return;

    let saved = null;
    try {
      saved = JSON.parse(window.sessionStorage.getItem(key) || "null");
    } catch (error) {
      saved = null;
    }

    if (saved) {
      const changed = [];
      saved.controls.forEach(function (state) {
        const candidates = Array.from(form.elements).filter((control) => control.name === state.name);
        const control = candidates[state.ordinal];
        if (!control || control.type === "file") return;

        if (control.tagName === "SELECT" && control.multiple) {
          const selected = new Set(state.values || []);
          Array.from(control.options).forEach((option) => { option.selected = selected.has(option.value); });
        } else if (control.type === "checkbox" || control.type === "radio") {
          control.checked = Boolean(state.checked);
        } else {
          control.value = state.value ?? "";
        }
        changed.push(control);
      });
      changed.forEach(dispatchFieldChange);
    }

    const relationFieldId = params.get("filmerp_related_field") || saved?.relationFieldId;
    const relatedId = params.get("filmerp_related_id");
    const relatedLabel = params.get("filmerp_related_label") || relatedId;
    const relationField = relationFieldId ? document.getElementById(relationFieldId) : null;
    if (relationField && relatedId) {
      if (relationField.tagName === "SELECT") {
        let option = Array.from(relationField.options).find((item) => item.value === relatedId);
        if (!option) {
          option = new Option(relatedLabel, relatedId, true, true);
          relationField.add(option);
        }
        if (!relationField.multiple) {
          Array.from(relationField.options).forEach((item) => { item.selected = item === option; });
        } else {
          option.selected = true;
        }
      } else {
        relationField.value = relatedId;
      }
      dispatchFieldChange(relationField);
    }

    try {
      window.sessionStorage.removeItem(key);
    } catch (error) {
      // Stan formularza jest jednorazowy; brak storage nie blokuje powrotu.
    }
    helperParams.forEach((name) => params.delete(name));
    const cleanUrl = `${window.location.pathname}${params.toString() ? `?${params}` : ""}${window.location.hash}`;
    window.history.replaceState({}, "", cleanUrl);
    window.requestAnimationFrame(function () {
      window.requestAnimationFrame(() => window.scrollTo({ top: saved?.y || 0, behavior: "auto" }));
    });
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
      Array.from(control.childNodes).forEach(function (child) {
        if (child.nodeType === Node.TEXT_NODE) child.remove();
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
    document.querySelectorAll(".related-widget-wrapper").forEach(function (wrapper) {
      if (wrapper.querySelector(".change-related")) {
        wrapper.querySelector(".view-related")?.remove();
      }
    });
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
    document.querySelectorAll(".add-related, .change-related, .view-related").forEach(function (link) {
      link.removeAttribute("target");
      link.removeAttribute("data-popup");
      link.addEventListener("click", function (event) {
        const navigation = relationNavigation(link);
        if (!navigation) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        const parentKey = snapshotParentForm(navigation.relationFieldId);
        if (parentKey) {
          navigation.target.searchParams.set("filmerp_parent_key", parentKey);
          navigation.target.searchParams.set("filmerp_parent_field", navigation.relationFieldId);
        }
        rememberScroll();
        window.location.assign(navigation.target.href);
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
    const queryParams = new URLSearchParams(window.location.search);
    const parentKey = queryParams.get("filmerp_parent_key");
    let cancelUrl = returnUrl;
    if (parentKey && sameOrigin(returnUrl)) {
      const parentUrl = new URL(returnUrl, window.location.href);
      parentUrl.searchParams.set("filmerp_restore", "1");
      parentUrl.searchParams.set("filmerp_parent_key", parentKey);
      cancelUrl = parentUrl.href;
    }

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
      cancel.href = cancelUrl;
      cancel.textContent = "Anuluj";
      cancel.addEventListener("click", rememberScroll);
      row.appendChild(cancel);
    });
  }

  function initializeAdminUx() {
    restoreParentFormState();
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
