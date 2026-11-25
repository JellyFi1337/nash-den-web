import { isCalm } from "./motion.js";
import { motionBoot } from "./time.js";

// Появление данных: числа докручиваются, полосы наливаются, ритм загорается волной,
// качество дня печатается. Всё — когда блок на экране, и только если данные новые:
// повторный заход на ту же страницу с теми же числами показывает их сразу.
const PENDING = "reveal-pending";
const INSTANT = "reveal-instant";
const STAGGER_MS = 70;
const TYPE_MS = 55;

export function initReveal() {
  const root = document.documentElement;
  const targets = collect();
  const moneyFrom = snapshotMoney(targets.counts);
  const count = Object.values(targets).reduce((sum, list) => sum + list.length, 0);
  const fresh = count > 0 && !isCalm() && "IntersectionObserver" in window && remember(targets);
  if (!fresh) {
    settle(root);
    return;
  }
  const plays = new Map();
  targets.counts.forEach((el) => {
    const play = el.dataset.countup === "money" ? armMoney(el, moneyFrom.get(el)) : armCount(el);
    if (play) {
      plays.set(el, play);
    }
  });
  // Полосы ждут свою карточку целиком: тонкую полосу в 8 px наблюдатель может пропустить.
  groupBy(targets.bars, (el) => el.closest(".person, .card, section") || el.parentElement).forEach(
    (list, owner) => {
      list.forEach((el) => {
        el.style.width = "0";
      });
      plays.set(owner, () => stagger(list, (el) => (el.style.width = "")));
    },
  );
  groupBy(targets.cols, (el) => el.parentElement).forEach((list, owner) => {
    list.forEach((el) => {
      el.style.height = "0";
    });
    plays.set(owner, () => stagger(list, (el) => (el.style.height = ""), 45));
  });
  targets.heats.forEach((heat) => plays.set(heat, armHeat(heat)));
  targets.types.forEach((el) => plays.set(el, armType(el)));
  root.classList.remove(PENDING);
  if (!plays.size) {
    return;
  }

  let timer = 0;
  const run = (el) => {
    const play = plays.get(el);
    if (!play) {
      return;
    }
    plays.delete(el);
    observer.unobserve(el);
    play();
    if (!plays.size) {
      window.removeEventListener("scroll", onScroll);
    }
  };
  const observer = new IntersectionObserver(
    (entries) => entries.forEach((entry) => entry.isIntersecting && run(entry.target)),
    { threshold: 0.2, rootMargin: "0px 0px -6% 0px" },
  );
  // Страховка на случай, если наблюдатель промолчал: при прокрутке сверяемся с экраном сами.
  const sweep = () => {
    timer = 0;
    const bottom = window.innerHeight * 0.94;
    [...plays.keys()].forEach((el) => {
      const rect = el.getBoundingClientRect();
      if ((rect.width || rect.height) && rect.top < bottom && rect.bottom > 0) {
        run(el);
      }
    });
  };
  const onScroll = () => {
    if (!timer) {
      timer = window.setTimeout(sweep, 120);
    }
  };
  plays.forEach((_play, el) => observer.observe(el));
  window.addEventListener("scroll", onScroll, { passive: true });
}

function collect() {
  // Внутри свёрнутого <details> блок не виден, наблюдатель его не заметит: такие не трогаем.
  const pick = (selector) =>
    [...document.querySelectorAll(selector)].filter((el) => !el.closest("details"));
  return {
    counts: pick("[data-countup]"),
    bars: pick(".bar > i"),
    cols: pick(".cols > i"),
    heats: pick(".heat"),
    types: pick("[data-type]"),
  };
}

// Подпись данных страницы. Совпала с прошлой в этой вкладке — показываем без анимации.
function remember(targets) {
  const parts = [
    ...targets.counts.map((el) => el.textContent.trim()),
    ...targets.bars.map((el) => el.style.getPropertyValue("--v") || el.getAttribute("style") || ""),
    ...targets.cols.map((el) => el.getAttribute("style") || ""),
    ...targets.heats.map((el) => [...el.querySelectorAll("[data-l]")].map((c) => c.dataset.l).join("")),
    ...targets.types.map((el) => el.textContent.trim()),
  ];
  const key = `nashden-reveal:${window.location.pathname}`;
  const sign = hash(parts.join("|"));
  try {
    if (window.sessionStorage.getItem(key) === sign) {
      return false;
    }
    window.sessionStorage.setItem(key, sign);
  } catch (error) {
    // Без хранилища анимация просто играет при каждом заходе.
  }
  return true;
}

function settle(root) {
  root.classList.add(INSTANT);
  root.classList.remove(PENDING);
  void root.offsetHeight;
  window.requestAnimationFrame(() => root.classList.remove(INSTANT));
}

function armCount(el) {
  const final = el.textContent.trim();
  const plan = parse(final);
  if (!plan) {
    return null;
  }
  el.textContent = plan.format(plan.from);
  return () => runCount(el, final, plan);
}

// Сумма банка: от прошлого значения в браузере, а не с нуля.
// Прошлого нет или оно то же — число сразу, короткое проявление.
function armMoney(el, previous) {
  const final = el.textContent.trim();
  const plan = parse(final);
  if (!plan || plan.time) {
    return null;
  }
  const known = typeof previous === "number" && Number.isFinite(previous);
  if (!known || previous === plan.to) {
    el.classList.add("is-ready");
    window.setTimeout(() => el.classList.remove("is-ready"), 700);
    return null;
  }
  const start = { ...plan, from: previous };
  el.textContent = start.format(previous);
  return () => runCount(el, final, start);
}

function snapshotMoney(counts) {
  const from = new Map();
  counts.forEach((el) => {
    if (el.dataset.countup !== "money") {
      return;
    }
    const plan = parse(el.textContent.trim());
    if (!plan || plan.time) {
      return;
    }
    from.set(el, readMoney(el));
    writeMoney(el, plan.to);
  });
  return from;
}

function moneyKey(el) {
  return `nashden-money:${el.dataset.countupKey || "bank"}`;
}

function readMoney(el) {
  try {
    const raw = window.localStorage.getItem(moneyKey(el));
    if (raw === null || raw === "") {
      return null;
    }
    const value = Number(raw);
    return Number.isFinite(value) ? value : null;
  } catch (error) {
    return null;
  }
}

function writeMoney(el, value) {
  try {
    window.localStorage.setItem(moneyKey(el), String(value));
  } catch (error) {
    // Хранилище закрыто: сумма просто показывается как есть.
  }
}

function runCount(el, final, plan) {
  const width = el.getBoundingClientRect().width;
  el.style.minWidth = `${Math.ceil(width)}px`;
  const span = Math.abs(plan.to - plan.from);
  const duration = plan.time ? 1100 : 600 + Math.min(600, Math.log10(span + 1) * 260);
  const started = performance.now();
  let done = false;
  const finish = () => {
    done = true;
    el.textContent = final;
    el.style.minWidth = "";
  };
  const step = (now) => {
    if (done) {
      return;
    }
    const progress = Math.min((now - started) / duration, 1);
    const eased = 1 - (1 - progress) ** 4;
    el.textContent = plan.format(Math.round(plan.from + (plan.to - plan.from) * eased));
    if (progress < 1) {
      window.requestAnimationFrame(step);
      return;
    }
    finish();
  };
  window.requestAnimationFrame(step);
  // Кадров может не быть (фоновая вкладка): итоговое число встаёт по таймеру.
  window.setTimeout(() => done || finish(), duration + 250);
}

function parse(text) {
  const time = /^(\d{1,2}):(\d{2})$/.exec(text);
  if (time) {
    const to = Number(time[1]) * 60 + Number(time[2]);
    const boot = motionBoot();
    const dayStart = (boot ? Number(boot.split) : 5) * 60;
    const from = Math.min(dayStart, to);
    if (from === to) {
      return null;
    }
    const pad = (value) => String(value).padStart(2, "0");
    return {
      time: true,
      from,
      to,
      format: (value) => `${pad(Math.floor(value / 60))}:${pad(value % 60)}`,
    };
  }
  const number = /^(\d{1,3}(?:([   ])\d{3})*)(\D.*)?$/su.exec(text);
  if (!number) {
    return null;
  }
  const sep = number[2] || "";
  const to = Number(number[1].replace(/[   ]/gu, ""));
  if (!to) {
    return null;
  }
  const rest = number[3] || "";
  return {
    time: false,
    from: 0,
    to,
    format: (value) => {
      const digits = String(value);
      return (sep ? digits.replace(/\B(?=(\d{3})+(?!\d))/gu, sep) : digits) + rest;
    },
  };
}

function armHeat(heat) {
  const rows = [...heat.querySelectorAll(".heat__row")];
  rows.forEach((row, rowIndex) => {
    [...row.querySelectorAll(".heat__cell")].forEach((cell, colIndex) => {
      cell.style.transitionDelay = `${colIndex * 32 + rowIndex * 16}ms`;
    });
  });
  heat.classList.add("is-armed");
  return () => {
    heat.classList.add("is-in");
    // После волны клетки возвращаются к обычным стилям: наведение увеличивает их без задержки.
    window.setTimeout(() => {
      heat.querySelectorAll(".heat__cell").forEach((cell) => {
        cell.style.transitionDelay = "";
      });
      heat.classList.remove("is-armed", "is-in");
    }, 1600);
  };
}

function armType(el) {
  const text = el.textContent;
  el.textContent = "";
  el.classList.add("is-typing");
  return () => {
    let index = 0;
    const timer = window.setInterval(() => {
      index += 1;
      el.textContent = text.slice(0, index);
      if (index >= text.length) {
        window.clearInterval(timer);
        window.setTimeout(() => el.classList.remove("is-typing"), 1400);
      }
    }, TYPE_MS);
  };
}

// Нулевое начальное состояние выставлено ещё при загрузке, поэтому кадр ждать не нужно:
// запуск по таймеру не зависит от того, отдаёт ли браузер кадры в эту секунду.
function stagger(list, apply, step = STAGGER_MS) {
  list.forEach((el, index) => window.setTimeout(() => apply(el), index * step));
}

function groupBy(list, key) {
  const groups = new Map();
  list.forEach((el) => {
    const owner = key(el);
    if (!groups.has(owner)) {
      groups.set(owner, []);
    }
    groups.get(owner).push(el);
  });
  return groups;
}

function hash(text) {
  let value = 5381;
  for (let index = 0; index < text.length; index += 1) {
    value = ((value << 5) + value + text.charCodeAt(index)) | 0;
  }
  return String(value >>> 0);
}
