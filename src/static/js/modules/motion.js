import { onPrefs } from "./prefs.js";

// Настройка движения: системная «уменьшить движение» или выбор в меню настроек.
// Спокойный режим: фон застывает, цифры меняются без прокрутки, искр и конфетти нет.
const media = window.matchMedia("(prefers-reduced-motion: reduce)");
const listeners = new Set();

export function isCalm() {
  return media.matches || document.documentElement.dataset.motion === "calm";
}

export function isSystemCalm() {
  return media.matches;
}

export function onCalmChange(listener) {
  listeners.add(listener);
}

function notify() {
  const calm = isCalm();
  listeners.forEach((listener) => listener(calm));
}

if (media.addEventListener) {
  media.addEventListener("change", notify);
}

onPrefs((name) => {
  if (name === "motion") {
    notify();
  }
});

// Переход между страницами — тоже движение: в спокойном режиме его пропускаем.
["pageswap", "pagereveal"].forEach((name) => {
  window.addEventListener(name, (event) => {
    const transition = event.viewTransition;
    if (!transition) {
      return;
    }
    // Пропущенный переход (наш или браузера в скрытой вкладке) отклоняет ready —
    // это ожидаемо и не должно сыпаться ошибкой в консоль.
    transition.ready.catch(() => {});
    if (isCalm()) {
      transition.skipTransition();
    }
  });
});
