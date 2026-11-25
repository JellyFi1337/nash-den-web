(function () {
  var root = document.documentElement;
  var stored = "1";
  var motion = "";
  var look = {};
  try {
    stored = localStorage.getItem("nashden-scale") || "1";
    motion = localStorage.getItem("nashden-motion") || "";
    look = JSON.parse(localStorage.getItem("nashden-look") || "{}") || {};
  } catch (error) {
    stored = "1";
    look = {};
  }
  if (stored === "2" || stored === "3") {
    root.dataset.scale = stored;
  }
  if (motion === "calm") {
    root.dataset.motion = "calm";
  }
  // Палитра, фон и эффекты из меню настроек — до отрисовки, чтобы не мигнуть чужим видом.
  // Список значений повторяет CHOICES из modules/prefs.js.
  var allowed = {
    scene: ["morning", "day", "evening", "night"],
    bg: ["off", "quiet", "normal", "bright"],
    palette: ["vivid", "quiet"],
    comets: ["off"],
    spot: ["off"],
    sparks: ["off"],
  };
  for (var key in allowed) {
    if (Object.prototype.hasOwnProperty.call(allowed, key) && allowed[key].indexOf(look[key]) !== -1) {
      root.dataset[key] = look[key];
    }
  }
  if (allowed.bg.indexOf(look.bg) !== -1) {
    root.dataset.bgExplicit = "1";
  }
  // Тема до первой отрисовки. data-theme — уже выбранный свет или тьма,
  // data-theme-pref хранит «как в системе», если человек выбрал иначе.
  var themePref = look.theme === "light" || look.theme === "dark" ? look.theme : "auto";
  var scheme = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  function resolvedTheme() {
    if (root.dataset.themeLock === "light") {
      return "light";
    }
    if (themePref === "dark" || themePref === "light") {
      return themePref;
    }
    return scheme && scheme.matches ? "dark" : "light";
  }
  function paintChrome() {
    var meta = document.querySelector('meta[name="theme-color"]');
    if (!meta) {
      return;
    }
    if (root.dataset.chrome === "gate") {
      meta.setAttribute("content", "#0B0B0C");
      return;
    }
    meta.setAttribute("content", root.dataset.theme === "dark" ? "#111113" : "#F4F2EC");
  }
  if (themePref !== "auto") {
    root.dataset.themePref = themePref;
  }
  root.dataset.theme = resolvedTheme();
  paintChrome();
  if (scheme && scheme.addEventListener) {
    scheme.addEventListener("change", function () {
      if (root.dataset.themeLock === "light" || root.dataset.themePref === "light" || root.dataset.themePref === "dark") {
        return;
      }
      root.dataset.theme = scheme.matches ? "dark" : "light";
      paintChrome();
      document.dispatchEvent(new CustomEvent("nashden:theme"));
    });
  }
  // Переход между страницами показывается новой странице раньше, чем загрузятся модули:
  // здесь пропускаем его в спокойном режиме и гасим отклонённое ready пропущенного перехода,
  // иначе в консоль падает «Transition was skipped».
  window.addEventListener("pagereveal", function (event) {
    var transition = event.viewTransition;
    if (!transition) {
      return;
    }
    transition.ready.catch(function () {});
    var system = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (system || root.dataset.motion === "calm") {
      transition.skipTransition();
    }
  });
  // Числа и полосы ждут скрипта появления, чтобы не мигнуть итоговым значением.
  // Если скрипт не загрузится, через 3 секунды всё показывается как есть.
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!reduce && motion !== "calm") {
    root.classList.add("reveal-pending");
    window.setTimeout(function () {
      root.classList.remove("reveal-pending");
    }, 3000);
  }
})();
