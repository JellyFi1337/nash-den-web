import { backgroundPolicy } from "./background-policy.js";

// Настройки вида в этом браузере: движение, размер текста, фон, палитра, эффекты.
// Источник правды после загрузки — атрибуты data-* на <html>: их ставит early.js
// до отрисовки, поэтому страница не мигает чужой палитрой или размером.
const LOOK_KEY = "nashden-look";
// Движение и размер жили в своих ключах до меню настроек — старый выбор сохраняется.
const SCALE_KEY = "nashden-scale";
const MOTION_KEY = "nashden-motion";

export const DEFAULTS = Object.freeze({
  motion: "full",
  scale: "1",
  scene: "auto",
  bg: "normal",
  palette: "soft",
  theme: "auto",
  comets: "on",
  spot: "on",
  sparks: "on",
});

export const CHOICES = Object.freeze({
  motion: ["full", "calm"],
  scale: ["1", "2", "3"],
  scene: ["auto", "morning", "day", "evening", "night"],
  bg: ["off", "quiet", "normal", "bright"],
  palette: ["soft", "vivid", "quiet"],
  theme: ["auto", "light", "dark"],
  comets: ["on", "off"],
  spot: ["on", "off"],
  sparks: ["on", "off"],
});

const LOOK = ["scene", "bg", "palette", "theme", "comets", "spot", "sparks"];
const root = document.documentElement;
const listeners = new Set();
let backgroundExplicit = root.dataset.bgExplicit === "1";
let backgroundValue = backgroundExplicit ? root.dataset.bg || "normal" : "normal";

function applyBackground() {
  const result = backgroundPolicy(backgroundValue, backgroundExplicit, {
    saveData: Boolean(navigator.connection?.saveData),
    cores: navigator.hardwareConcurrency || 8,
    memory: navigator.deviceMemory || 8,
  });
  if (result.value === "normal") {
    delete root.dataset.bg;
  } else {
    root.dataset.bg = result.value;
  }
  root.toggleAttribute("data-bg-economical", result.economical);
}

export function isBackgroundEconomical() {
  return root.hasAttribute("data-bg-economical");
}

applyBackground();
navigator.connection?.addEventListener?.("change", () => {
  applyBackground();
  listeners.forEach((listener) => listener("bg", getPref("bg")));
});

export function getPref(name) {
  if (name === "theme") {
    const value = root.dataset.themePref;
    return CHOICES.theme.includes(value) ? value : "auto";
  }
  const value = root.dataset[name];
  return CHOICES[name] && CHOICES[name].includes(value) ? value : DEFAULTS[name];
}

function paintChrome() {
  const meta = document.querySelector('meta[name="theme-color"]');
  if (!meta) {
    return;
  }
  if (root.dataset.chrome === "gate") {
    meta.setAttribute("content", "#0B0B0C");
    return;
  }
  meta.setAttribute("content", root.dataset.theme === "dark" ? "#111113" : "#F4F2EC");
}

function applyTheme() {
  if (root.dataset.themeLock === "light") {
    root.dataset.theme = "light";
    paintChrome();
    return;
  }
  const pref = getPref("theme");
  const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  root.dataset.theme = pref === "auto" ? (dark ? "dark" : "light") : pref;
  paintChrome();
  document.dispatchEvent(new CustomEvent("nashden:theme"));
}

export function setPref(name, value) {
  if (!CHOICES[name] || !CHOICES[name].includes(value)) {
    return;
  }
  if (name === "bg") {
    backgroundExplicit = true;
    backgroundValue = value;
    root.dataset.bgExplicit = "1";
    applyBackground();
    save(name);
    listeners.forEach((listener) => listener(name, value));
    return;
  }
  if (getPref(name) === value) {
    return;
  }
  if (name === "theme") {
    if (value === "auto") {
      delete root.dataset.themePref;
    } else {
      root.dataset.themePref = value;
    }
    applyTheme();
    save(name);
    listeners.forEach((listener) => listener(name, value));
    return;
  }
  if (value === DEFAULTS[name]) {
    delete root.dataset[name];
  } else {
    root.dataset[name] = value;
  }
  save(name);
  listeners.forEach((listener) => listener(name, value));
}

export function resetPrefs() {
  backgroundExplicit = false;
  backgroundValue = "normal";
  delete root.dataset.bgExplicit;
  Object.keys(DEFAULTS).filter((name) => name !== "bg").forEach((name) => setPref(name, DEFAULTS[name]));
  applyBackground();
  save("bg");
  listeners.forEach((listener) => listener("bg", getPref("bg")));
}

export function onPrefs(listener) {
  listeners.add(listener);
}

function save(name) {
  try {
    if (name === "scale") {
      localStorage.setItem(SCALE_KEY, getPref("scale"));
    } else if (name === "motion") {
      localStorage.setItem(MOTION_KEY, getPref("motion"));
    } else {
      const look = {};
      LOOK.forEach((key) => {
        if (key === "bg") {
          if (backgroundExplicit) {
            look.bg = backgroundValue;
          }
          return;
        }
        if (getPref(key) !== DEFAULTS[key]) {
          look[key] = getPref(key);
        }
      });
      localStorage.setItem(LOOK_KEY, JSON.stringify(look));
    }
  } catch (error) {
    // Хранилище закрыто (приватный режим): выбор действует до закрытия вкладки.
  }
}
