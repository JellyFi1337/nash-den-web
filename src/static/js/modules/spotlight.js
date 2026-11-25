import { isCalm } from "./motion.js";
import { getPref } from "./prefs.js";

// Свет за курсором на карточках (только мышь) и мягкий круг из точки касания на телефоне.
const RIPPLE_MS = 650;

export function initSpotlight() {
  const fine = window.matchMedia("(hover: hover) and (pointer: fine)");
  let latest = null;
  let frame = 0;
  document.addEventListener(
    "pointermove",
    (event) => {
      if (!fine.matches || event.pointerType !== "mouse") {
        return;
      }
      latest = event;
      if (frame) {
        return;
      }
      frame = window.requestAnimationFrame(() => {
        frame = 0;
        const target = latest.target instanceof Element ? latest.target : null;
        const card = target ? target.closest(".card") : null;
        if (!card) {
          return;
        }
        const rect = card.getBoundingClientRect();
        card.style.setProperty("--spot-x", `${Math.round(latest.clientX - rect.left)}px`);
        card.style.setProperty("--spot-y", `${Math.round(latest.clientY - rect.top)}px`);
      });
    },
    { passive: true },
  );
  document.addEventListener(
    "pointerdown",
    (event) => {
      if (event.pointerType !== "touch" || isCalm() || getPref("spot") === "off") {
        return;
      }
      const target = event.target instanceof Element ? event.target : null;
      if (!target || !target.closest("a, button, summary")) {
        return;
      }
      const dot = document.createElement("span");
      dot.className = "tap-ripple";
      dot.setAttribute("aria-hidden", "true");
      dot.style.left = `${event.clientX}px`;
      dot.style.top = `${event.clientY}px`;
      document.body.appendChild(dot);
      window.setTimeout(() => dot.remove(), RIPPLE_MS);
    },
    { passive: true },
  );
}
