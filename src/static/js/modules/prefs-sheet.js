import { isCalm } from "./motion.js";

// Мобильный лист живёт поверх страницы; настольное раскрытие остаётся обычным details.
export function createPrefsSheet(box, panel, summary, close) {
  const mobile = window.matchMedia("(max-width: 59.99rem)");
  let locked = false;
  let scrollY = 0;
  let scrollbar = 0;
  let inert = [];
  let drag = null;
  let settling = 0;
  let prepared = null;
  const body = document.body;
  const root = document.documentElement;

  const focusable = () => [...panel.querySelectorAll('button, a[href], input, [tabindex="0"]')].filter((el) => {
    if (el.disabled || !el.getClientRects().length) {
      return false;
    }
    if (el.type !== "radio") {
      return true;
    }
    const group = [...panel.querySelectorAll('input[type="radio"]')].filter((other) => other.name === el.name && !other.disabled);
    return el.checked || (!group.some((other) => other.checked) && el === group[0]);
  });
  const focusFirst = () => focusable()[0]?.focus({ preventScroll: true });

  const unlock = () => {
    if (!locked) {
      return;
    }
    locked = false;
    root.classList.remove("has-prefs-sheet");
    body.classList.remove("has-prefs-sheet");
    body.style.removeProperty("--prefs-scroll-y");
    body.style.removeProperty("--prefs-page-width");
    inert.forEach((el) => { el.inert = false; });
    inert = [];
    panel.removeAttribute("role");
    panel.removeAttribute("aria-modal");
    panel.removeAttribute("aria-labelledby");
    window.scrollTo({ top: scrollY, behavior: "instant" });
  };
  const sync = () => {
    if (!box.open || !mobile.matches) {
      unlock();
      return;
    }
    if (locked) {
      return;
    }
    // details может сам прокрутить страницу до события toggle: положение берём до открытия.
    scrollY = prepared?.y ?? window.scrollY;
    scrollbar = prepared?.scrollbar ?? window.innerWidth - root.clientWidth;
    body.style.setProperty("--prefs-scroll-y", `${-scrollY}px`);
    body.style.setProperty("--prefs-page-width", `${prepared?.width ?? body.getBoundingClientRect().width}px`);
    prepared = null;
    root.classList.add("has-prefs-sheet");
    body.classList.add("has-prefs-sheet");
    // Отключаем соседей по пути к body, не делая саму шапку с меню inert.
    for (let branch = box; branch.parentElement && branch !== body; branch = branch.parentElement) {
      [...branch.parentElement.children].forEach((el) => {
        if (el !== branch && el instanceof HTMLElement && !el.inert && !["SCRIPT", "STYLE", "TEMPLATE"].includes(el.tagName)) {
          el.inert = true;
          inert.push(el);
        }
      });
    }
    locked = true;
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-modal", "true");
    panel.setAttribute("aria-labelledby", "prefs-title");
    focusFirst();
  };
  const clearDrag = () => {
    window.clearTimeout(settling);
    drag = null;
    panel.classList.remove("is-dragging", "is-settling");
    panel.style.removeProperty("transform");
    panel.style.removeProperty("--prefs-drag-offset");
  };
  const settle = () => {
    panel.classList.remove("is-dragging");
    if (isCalm()) {
      clearDrag();
      return;
    }
    panel.classList.add("is-settling");
    // Таймер страхует очистку и в фоновой вкладке.
    settling = window.setTimeout(clearDrag, 240);
    window.requestAnimationFrame(() => { if (!drag) { panel.style.transform = ""; } });
  };

  document.addEventListener("focusin", (event) => {
    if (locked && box.open && !panel.contains(event.target)) {
      focusFirst();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Tab" || !locked || !box.open) {
      return;
    }
    const elements = focusable();
    const first = elements[0];
    const last = elements.at(-1);
    if ((event.shiftKey && document.activeElement === first) || (!event.shiftKey && document.activeElement === last)) {
      event.preventDefault();
      (event.shiftKey ? last : first)?.focus();
    }
  });
  panel.addEventListener("pointerdown", (event) => {
    if (!mobile.matches || !box.open || event.button !== 0 || box.classList.contains("is-closing")) {
      return;
    }
    const target = event.target instanceof Element ? event.target : null;
    if (!target?.closest("[data-prefs-handle], .prefs__head") || target.closest("button, a, input")) {
      return;
    }
    clearDrag();
    drag = { id: event.pointerId, y: event.clientY, time: event.timeStamp, offset: 0 };
    panel.setPointerCapture(event.pointerId);
    panel.classList.add("is-dragging");
  });
  panel.addEventListener("pointermove", (event) => {
    if (!drag || drag.id !== event.pointerId) {
      return;
    }
    drag.offset = Math.max(0, event.clientY - drag.y);
    panel.style.transform = `translateY(${drag.offset}px)`;
    event.preventDefault();
  });
  const end = (event) => {
    if (!drag || drag.id !== event.pointerId) {
      return;
    }
    const { offset, time } = drag;
    const speed = offset / Math.max(1, event.timeStamp - time);
    drag = null;
    if (panel.hasPointerCapture(event.pointerId)) {
      panel.releasePointerCapture(event.pointerId);
    }
    panel.classList.remove("is-dragging");
    if (event.type === "pointerup" && (offset >= 80 || (offset >= 24 && speed >= 0.6))) {
      panel.style.setProperty("--prefs-drag-offset", `${offset}px`);
      panel.style.transform = "";
      close(true);
    } else {
      settle();
    }
  };
  panel.addEventListener("pointerup", end);
  panel.addEventListener("pointercancel", end);
  mobile.addEventListener("change", sync);
  window.addEventListener("resize", () => {
    if (locked) {
      body.style.setProperty("--prefs-page-width", `${window.innerWidth - scrollbar}px`);
    }
  }, { passive: true });
  window.addEventListener("pagehide", unlock);
  return {
    prepare: () => {
      if (mobile.matches) {
        prepared = { y: window.scrollY, width: body.getBoundingClientRect().width, scrollbar: window.innerWidth - root.clientWidth };
      }
    },
    sync,
    isMobile: () => mobile.matches,
    closed: () => { clearDrag(); unlock(); prepared = null; },
  };
}
