import { confetti } from "./fx.js";
import { isCalm } from "./motion.js";
import { tapHaptic } from "./haptics.js";

const SHOWN_MS = 1500;
const OPEN_MS = 600;
const memory = new Set();

export function initCelebrate() {
  const boot = readBoot();
  if (boot.source === "report" || boot.source === "none") {
    return;
  }
  const morning = document.querySelector('[data-odo][data-side="morning"]');
  const evening = document.querySelector('[data-odo][data-side="evening"]');
  if (!boot.day || !morning || !evening) {
    return;
  }
  maybeCelebrate(boot.day, "morning", Number(morning.dataset.count), Number(morning.dataset.total));
  maybeCelebrate(boot.day, "evening", Number(evening.dataset.count), Number(evening.dataset.total));
}

export function maybeCelebrate(day, kind, count, total) {
  if (!day || !total || count !== total) {
    return;
  }
  const key = `nashden-celebrate:${day}:${kind}`;
  if (memory.has(key) || stored(key)) {
    return;
  }
  memory.add(key);
  save(key);
  const node = document.querySelector("[data-celebrate]");
  if (!node) {
    return;
  }
  const num = node.querySelector("[data-celebrate-num]");
  if (num) {
    num.textContent = `${count}/${total}`;
  }
  node.setAttribute("aria-hidden", "false");
  const reduced = isCalm();
  if (reduced) {
    node.style.transition = "none";
    node.style.clipPath = "circle(150% at 50% 30%)";
  }
  node.classList.add("is-on");
  tapHaptic();
  window.setTimeout(() => {
    node.style.clipPath = "circle(150% at 50% 30%)";
  }, reduced ? 0 : OPEN_MS);
  // Конфетти поверх заливки — один раз за день вместе с ней.
  window.setTimeout(confetti, reduced ? 0 : OPEN_MS / 2);
  window.setTimeout(() => {
    node.classList.remove("is-on");
    node.style.clipPath = "";
    node.setAttribute("aria-hidden", "true");
  }, SHOWN_MS);
}

function readBoot() {
  const node = document.getElementById("pulse-boot");
  if (!node) {
    return {};
  }
  try {
    return JSON.parse(node.textContent || "{}");
  } catch (error) {
    return {};
  }
}

function stored(key) {
  try {
    return window.localStorage.getItem(key) === "1";
  } catch (error) {
    return false;
  }
}

function save(key) {
  try {
    window.localStorage.setItem(key, "1");
  } catch (error) {
    /* хранилище закрыто — повтор в этом браузере останется только до закрытия вкладки */
  }
}
