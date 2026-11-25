import { isCalm } from "./motion.js";
import { isRippleSkipped, requestRippleSkip, resetRippleSkip, ripple } from "./ripple.js";

const SEEN_KEY = "nashden-gate-day";
const FULL_RIPPLE_MS = 1800;
const FULL_RIPPLE_FROM = 70;
const SHORT_RIPPLE_MS = 700;
const SHORT_RIPPLE_FROM = 60;
const FAIL_RIPPLE_MS = 320;
const FAIL_RIPPLE_FROM = 18;
const TYPE_DELAY_MS = 14;

export function initGate() {
  const gate = document.querySelector("[data-gate]");
  if (!gate) {
    return;
  }
  const title = gate.querySelector("[data-gate-title]");
  const log = gate.querySelector("[data-gate-log]");
  const form = gate.querySelector("[data-gate-form]");
  const input = gate.querySelector("[data-gate-code]");
  const hint = gate.querySelector("[data-gate-hint]");
  const reveal = document.querySelector("[data-reveal]");
  // «Спокойное движение» из меню действует и здесь: заставка не играет сама.
  const reduced = isCalm();
  const weak = isWeakDevice();
  const siteDay = gate.dataset.siteDay || "";
  const lockedSeconds = Number(gate.dataset.lockedSeconds || "0");
  const newDay = gate.dataset.newDay === "1";
  const feedback = gate.dataset.feedback === "1";

  input.addEventListener("paste", (event) => {
    const text = event.clipboardData?.getData("text/plain");
    if (typeof text !== "string") {
      return;
    }
    event.preventDefault();
    input.setRangeText(cleanPastedCode(text), input.selectionStart, input.selectionEnd, "end");
  });
  const paste = gate.querySelector("[data-gate-paste]");
  if (paste && window.isSecureContext && navigator.clipboard?.readText) {
    paste.hidden = false;
    paste.addEventListener("click", async () => {
      try {
        input.value = cleanPastedCode(await navigator.clipboard.readText());
        focusCode(input);
      } catch (error) {
        hint.textContent = "Буфер недоступен. Вставьте код в поле вручную.";
        focusCode(input);
      }
    });
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!gate.classList.contains("is-ready") || input.disabled) {
      return;
    }
    submit(form, input, hint, title, reveal, reduced, weak);
  });

  const open = () => {
    openGate(gate, title, log, input, form, hint, reduced, weak, siteDay, lockedSeconds, newDay, feedback);
  };
  const replay = gate.querySelector("[data-gate-replay]");
  if (replay) {
    replay.addEventListener("click", () => replayIntro(gate, title, log, input, weak));
  }
  if (location.href.includes("tgWebAppData")) {
    enterFromTelegram(form).then((entered) => {
      if (!entered) {
        open();
      }
    });
    return;
  }
  open();
}

function openGate(gate, title, log, input, form, hint, reduced, weak, siteDay, lockedSeconds, newDay, feedback) {
  if (lockedSeconds > 0) {
    markReady(gate);
    startCountdown(input, form, hint, lockedSeconds);
    return;
  }
  if (feedback || reduced) {
    markReady(gate);
    focusCode(input);
    return;
  }
  armSkip(gate);
  if (newDay) {
    playNewDay(gate, title, weak, input);
    return;
  }
  if (seenToday(siteDay)) {
    showRestored(log);
    markReady(gate);
    focusCode(input);
    return;
  }
  playIntro(gate, title, log, siteDay, weak, input);
}

function enterFromTelegram(form) {
  return loadTelegramScript().then(() => postInitData(form));
}

function loadTelegramScript() {
  if (window.Telegram && window.Telegram.WebApp) {
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    const script = document.createElement("script");
    script.src = "https://telegram.org/js/telegram-web-app.js";
    script.onload = () => resolve();
    script.onerror = () => resolve();
    document.head.appendChild(script);
  });
}

async function postInitData(form) {
  const webApp = window.Telegram && window.Telegram.WebApp;
  const data = webApp ? webApp.initData || "" : "";
  if (!data) {
    return false;
  }
  const token = form.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
  try {
    const response = await fetch("/enter/telegram/", {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": token,
      },
      body: JSON.stringify({ init_data: data }),
      credentials: "same-origin",
    });
    if (!response.ok) {
      return false;
    }
    const payload = await response.json();
    if (payload.ok && payload.redirect) {
      window.location.assign(safeRedirect(payload.redirect));
      return true;
    }
  } catch (error) {
    return false;
  }
  return false;
}

function playIntro(gate, title, log, siteDay, weak, input) {
  title.classList.add("is-split");
  const wave = ripple(gate, FULL_RIPPLE_MS, FULL_RIPPLE_FROM, !weak);
  runIntro(title, log, wave).then(() => {
    rememberDay(siteDay);
    markReady(gate);
    focusCode(input);
  });
}

async function runIntro(title, log, wave) {
  await typeLine(log, "сбой контекста…", false);
  await pause(260);
  await typeLine(log, "пересборка дня…", false);
  await pause(420);
  title.classList.remove("is-split");
  await typeLine(log, "контекст восстановлен ✓", true);
  await wave;
}

let replaying = false;

// Заставку можно посмотреть ещё раз по нажатию на знак. Введённый код не теряется.
async function replayIntro(gate, title, log, input, weak) {
  if (replaying || !gate.classList.contains("is-ready")) {
    return;
  }
  replaying = true;
  const value = input.value;
  armSkip(gate);
  resetRippleSkip();
  gate.classList.remove("is-ready");
  gate.classList.add("is-replaying");
  log.replaceChildren();
  if (isCalm()) {
    // Спокойный режим: без ряби и расслоения, только строки журнала.
    await runIntro(title, log, Promise.resolve());
  } else {
    title.classList.add("is-split");
    await runIntro(title, log, ripple(gate, FULL_RIPPLE_MS, FULL_RIPPLE_FROM, !weak));
  }
  gate.classList.remove("is-replaying");
  input.value = value;
  markReady(gate);
  focusCode(input);
  replaying = false;
}

function armSkip(gate) {
  if (gate.dataset.skipArmed) {
    return;
  }
  gate.dataset.skipArmed = "1";
  const stop = () => {
    if (!gate.classList.contains("is-ready")) {
      requestRippleSkip();
    }
  };
  gate.addEventListener("pointerdown", stop);
  window.addEventListener("keydown", stop);
}

async function playNewDay(gate, title, weak, input) {
  title.classList.add("is-split");
  await ripple(gate, SHORT_RIPPLE_MS, SHORT_RIPPLE_FROM, !weak);
  title.classList.remove("is-split");
  markReady(gate);
  focusCode(input);
}

let sending = false;

async function submit(form, input, hint, title, reveal, reduced, weak) {
  if (input.disabled || sending) {
    return;
  }
  sending = true;
  const token = form.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
  const body = new FormData();
  body.set("code", input.value);
  body.set("csrfmiddlewaretoken", token);
  let data;
  try {
    const response = await fetch(form.action, {
      method: "POST",
      headers: { Accept: "application/json", "X-CSRFToken": token },
      body,
      credentials: "same-origin",
    });
    data = await response.json();
  } catch (error) {
    sending = false;
    hint.textContent = "Не удалось отправить код. Попробуйте ещё раз.";
    return;
  }
  if (data.ok) {
    input.classList.add("is-ok");
    if (!isCalm() && navigator.maxTouchPoints > 0) {
      navigator.vibrate?.(12);
    }
    if (!reduced) {
      await wait(420);
      if (reveal) {
        reveal.classList.add("is-on");
      }
      await wait(560);
    }
    window.location.assign(safeRedirect(data.redirect));
    return;
  }
  if (data.locked_seconds > 0) {
    startCountdown(input, form, hint, data.locked_seconds);
    return;
  }
  sending = false;
  input.classList.remove("is-bad");
  void input.offsetWidth;
  input.classList.add("is-bad");
  if (!isCalm()) {
    title.classList.add("is-split");
    ripple(form.closest("[data-gate]"), FAIL_RIPPLE_MS, FAIL_RIPPLE_FROM, !weak).then(
      () => {
        title.classList.remove("is-split");
      },
    );
  }
  const left = Number(data.attempts_left || 0);
  hint.textContent = "Код не подошёл. Код дня — у бота.";
  if (left <= 3) {
    hint.textContent += ` Осталось попыток: ${left}.`;
  }
}

function startCountdown(input, form, hint, seconds) {
  const buttons = form.querySelectorAll("button");
  input.disabled = true;
  buttons.forEach((button) => { button.disabled = true; });
  const deadline = Date.now() + seconds * 1000;
  const timer = document.createElement("span");
  timer.setAttribute("role", "timer");
  timer.setAttribute("aria-live", "off");
  hint.replaceChildren("Слишком много попыток. Попробуйте через ", timer, ".");
  const tick = () => {
    // Отсчёт не удлиняет паузу после ухода вкладки в фон.
    const left = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
    if (left <= 0) {
      input.disabled = false;
      buttons.forEach((button) => { button.disabled = false; });
      sending = false;
      hint.textContent = "Код дня — у бота.";
      focusCode(input);
      return;
    }
    const minutes = String(Math.floor(left / 60)).padStart(2, "0");
    const remainder = String(left % 60).padStart(2, "0");
    timer.textContent = `${minutes}:${remainder}`;
    window.setTimeout(tick, 1000);
  };
  tick();
}

function cleanPastedCode(text) {
  return text.replace(/^[\s"'«»„“”‘’]+|[\s"'«»„“”‘’]+$/gu, "");
}

function showRestored(log) {
  if (log.children.length > 0) {
    return;
  }
  const lines = [
    ["сбой контекста…", false],
    ["пересборка дня…", false],
    ["контекст восстановлен ✓", true],
  ];
  for (const [text, done] of lines) {
    const line = document.createElement("div");
    if (done) {
      line.className = "is-ok";
    }
    line.textContent = text;
    log.appendChild(line);
  }
}

async function typeLine(log, text, done) {
  const line = document.createElement("div");
  if (done) {
    line.className = "is-ok";
  }
  log.appendChild(line);
  for (const char of text) {
    line.textContent += char;
    if (isRippleSkipped()) {
      line.textContent = text;
      break;
    }
    await wait(TYPE_DELAY_MS);
  }
}

async function pause(milliseconds) {
  if (isRippleSkipped()) {
    return;
  }
  await wait(milliseconds);
}

function markReady(gate) {
  gate.classList.add("is-ready");
}

function focusCode(input) {
  if (!input.disabled) {
    input.focus();
  }
}

function seenToday(siteDay) {
  try {
    return localStorage.getItem(SEEN_KEY) === siteDay;
  } catch (error) {
    return false;
  }
}

function rememberDay(siteDay) {
  try {
    localStorage.setItem(SEEN_KEY, siteDay);
  } catch (error) {
    // Без хранилища полная последовательность повторится при следующем заходе.
  }
}

function isWeakDevice() {
  const cores = navigator.hardwareConcurrency || 8;
  const memory = navigator.deviceMemory || 8;
  return cores <= 4 || memory <= 2;
}

function safeRedirect(url) {
  if (typeof url !== "string" || !url.startsWith("/") || url.startsWith("//")) {
    return "/";
  }
  return url;
}

function wait(milliseconds) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, milliseconds);
  });
}
