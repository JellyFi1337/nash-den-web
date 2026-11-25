import { isCalm } from "./motion.js";

const THRESHOLD = 60;
const NUDGE_MS = 300;

export function initSwipe() {
  const root = document.querySelector("[data-swipe]");
  const bootNode = document.getElementById("day-swipe");
  if (!root || !bootNode) {
    return;
  }
  let boot = { prev: "", next: "" };
  try {
    boot = JSON.parse(bootNode.textContent || "{}");
  } catch (error) {
    boot = { prev: "", next: "" };
  }
  let start = null;

  document.addEventListener("pointerdown", (event) => {
    if (blocked(event.target)) {
      start = null;
      return;
    }
    start = { x: event.clientX, y: event.clientY };
  });
  document.addEventListener("pointerup", (event) => {
    if (!start) {
      return;
    }
    const dx = event.clientX - start.x;
    const dy = event.clientY - start.y;
    start = null;
    if (Math.abs(dx) < THRESHOLD || Math.abs(dx) < Math.abs(dy) * 1.5) {
      return;
    }
    go(dx < 0 ? "next" : "prev");
  });
  document.addEventListener("pointercancel", () => {
    start = null;
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") {
      return;
    }
    if (blocked(event.target) || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || document.querySelector("dialog[open]")) {
      return;
    }
    event.preventDefault();
    go(event.key === "ArrowRight" ? "next" : "prev");
  });

  function go(direction) {
    const url = direction === "next" ? boot.next : boot.prev;
    if (url) {
      window.location.assign(url);
      return;
    }
    nudge(root, direction);
  }
}

function blocked(target) {
  if (!(target instanceof Element)) {
    return false;
  }
  if (typing(target) || target.closest(".hscroll, .day-nav, dialog, button, a, summary")) {
    return true;
  }
  const details = target.closest("details");
  return Boolean(details && details.open);
}

function typing(target) {
  if (!(target instanceof Element)) {
    return false;
  }
  return Boolean(target.closest("input, textarea, select, [contenteditable='true']"));
}

function nudge(root, direction) {
  const reduced = isCalm();
  const name = direction === "next" ? "is-nudge-next" : "is-nudge-prev";
  root.classList.remove("is-nudge-next", "is-nudge-prev");
  if (!reduced) {
    window.setTimeout(() => {
      root.classList.add(name);
    }, 20);
  }
  window.setTimeout(() => {
    root.classList.remove("is-nudge-next", "is-nudge-prev");
  }, NUDGE_MS);
}
