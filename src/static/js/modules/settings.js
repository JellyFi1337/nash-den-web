import { isCalm, isSystemCalm, onCalmChange } from "./motion.js";
import { CHOICES, getPref, isBackgroundEconomical, onPrefs, resetPrefs, setPref } from "./prefs.js";
import { createPrefsSheet } from "./prefs-sheet.js";
import { tapHaptic } from "./haptics.js";

// Меню «вид и движение» в шапке. Без скриптов <details> всё равно открывается,
// а выход к вводу кода — обычная форма. Скрипт связывает переключатели с настройками,
// закрывает меню по Esc и щелчку мимо и проигрывает закрытие.
const PARTS = { morning: "утро", day: "день", evening: "вечер", night: "ночь" };
const CLOSE_MS = 220;

export function initSettings() {
  const box = document.querySelector("[data-prefs]");
  if (!box) {
    return;
  }
  const summary = box.querySelector("summary");
  const panel = box.querySelector("[data-prefs-panel]");
  const inputs = [...box.querySelectorAll("input[name]")].filter((input) => CHOICES[input.name]);

  const sync = () => {
    inputs.forEach((input) => {
      const value = getPref(input.name);
      if (input.type === "checkbox") {
        input.checked = value === "on";
      } else {
        input.checked = input.value === value;
      }
    });
    const system = isSystemCalm();
    box.querySelectorAll('input[name="motion"]').forEach((input) => {
      input.disabled = system;
      if (system) {
        input.checked = input.value === "calm";
      }
    });
    say(box, "motion", system ? "Спокойное движение включено в настройках устройства." : "");
    const auto = PARTS[document.documentElement.dataset.autopart] || "";
    say(box, "scene", auto ? `по времени суток в Москве сейчас ${auto}` : "");
    const preview = box.querySelector('[data-scene-preview="auto"], [data-auto-preview]');
    if (preview) {
      preview.dataset.autoPreview = "1";
      preview.dataset.scenePreview = document.documentElement.dataset.autopart || "day";
    }
    const caption = box.querySelector("[data-prefs-auto-caption]");
    if (caption) {
      caption.textContent = auto;
    }
    say(box, "economy", isBackgroundEconomical() ? "фон приглушён для экономии" : "");
    const theme = getPref("theme");
    const resolved = document.documentElement.dataset.theme === "dark" ? "тёмная" : "светлая";
    say(box, "theme", theme === "auto" ? `как в системе: сейчас ${resolved}` : "");
    box.classList.toggle("is-bg-off", getPref("bg") === "off");
  };

  inputs.forEach((input) => {
    if (input.name === "bg") {
      const choose = () => {
        if (input.checked && (getPref("bg") !== input.value || document.documentElement.dataset.bgExplicit !== "1")) {
          setPref("bg", input.value);
          tapHaptic();
        }
      };
      input.addEventListener("click", choose);
      input.addEventListener("change", choose);
      return;
    }
    input.addEventListener("change", () => {
      if (input.type === "checkbox") {
        setPref(input.name, input.checked ? "on" : "off");
      } else if (input.checked) {
        setPref(input.name, input.value);
      }
      tapHaptic();
    });
  });

  let closing = 0;
  let closingFocus = false;
  const finish = () => {
    window.clearTimeout(closing);
    closing = 0;
    box.classList.remove("is-closing");
    box.open = false;
    sheet.closed();
    if (closingFocus) {
      summary.focus({ preventScroll: true });
    }
  };
  const close = (focus) => {
    if (!box.open || closing) {
      return;
    }
    closingFocus = focus || sheet.isMobile();
    if (isCalm()) {
      finish();
      return;
    }
    box.classList.add("is-closing");
    // Страховочный таймер: в фоновой вкладке конец анимации может не прийти.
    closing = window.setTimeout(finish, CLOSE_MS);
  };
  const sheet = createPrefsSheet(box, panel, summary, close);

  summary.addEventListener("click", (event) => {
    if (box.open) {
      event.preventDefault();
      close(false);
    } else {
      sheet.prepare();
    }
  });
  box.addEventListener("toggle", () => {
    if (box.open) {
      sync();
    }
    sheet.sync();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && box.open) {
      event.preventDefault();
      close(true);
    }
  });
  document.addEventListener("pointerdown", (event) => {
    if (box.open && event.target instanceof Node && !box.contains(event.target)) {
      close(false);
    }
  });
  box.querySelector("[data-prefs-done]")?.addEventListener("click", () => close(true));
  box.querySelector("[data-prefs-reset]")?.addEventListener("click", () => {
    resetPrefs();
    tapHaptic();
    sync();
    document.dispatchEvent(
      new CustomEvent("nashden:toast", { detail: { text: "Вид как был по умолчанию", ms: 1800 } }),
    );
  });
  if (panel) {
    panel.addEventListener("animationend", (event) => {
      if (event.target === panel && box.classList.contains("is-closing")) {
        finish();
      }
    });
  }
  onPrefs(sync);
  onCalmChange(sync);
  document.addEventListener("nashden:daypart", sync);
  sync();
}

function say(box, name, text) {
  const note = box.querySelector(`[data-prefs-note="${name}"]`);
  if (!note) {
    return;
  }
  note.textContent = text;
  note.hidden = !text;
}
