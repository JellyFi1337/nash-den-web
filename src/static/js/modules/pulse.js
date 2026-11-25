import { setOdometer } from "./odometer.js";
import { maybeCelebrate } from "./celebrate.js";
import { sparksFrom } from "./fx.js";

const MAX_WAIT_MS = 5 * 60 * 1000;
const BAR_MS = 900;
const FLASH_MS = 900;
const MISSING = {
  1: "одного",
  2: "двоих",
  3: "троих",
  4: "четверых",
  5: "пятерых",
  6: "шестерых",
  7: "семерых",
  8: "восьмерых",
  9: "девятерых",
  10: "десятерых",
};
const STATUS = ["is-wait", "is-morning", "is-done"];

export function initPulse() {
  const root = document.querySelector("[data-pulse]");
  if (!root) {
    return;
  }
  const boot = readBoot();
  const seenEvents = new Set(boot.events || []);
  const seenAchievements = new Set(boot.achievements || []);
  const pollSeconds = Number(boot.poll_seconds) > 0 ? Number(boot.poll_seconds) : 45;
  let wait = pollSeconds * 1000;
  let timer = 0;

  const tick = async () => {
    if (document.hidden) {
      return;
    }
    try {
      const response = await fetch("/api/pulse/", {
        headers: { Accept: "application/json" },
        cache: "no-store",
        credentials: "same-origin",
      });
      if (response.status === 401) {
        window.location.assign("/enter/?new_day=1");
        return;
      }
      if (!response.ok) {
        throw new Error("pulse");
      }
      const data = await response.json();
      // Новый отчёт или подключённый чат меняет также строки команды и подпись даты.
      if (data.source !== boot.source || data.report_day !== boot.report_day) {
        window.location.reload();
        return;
      }
      apply(data, seenEvents, seenAchievements);
      wait = pollSeconds * 1000;
    } catch (error) {
      wait = Math.min(Math.max(wait * 2, 1000), MAX_WAIT_MS);
    }
    arm();
  };

  const arm = () => {
    window.clearTimeout(timer);
    if (document.hidden) {
      return;
    }
    timer = window.setTimeout(tick, wait);
  };

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      window.clearTimeout(timer);
      return;
    }
    wait = pollSeconds * 1000;
    tick();
  });
  arm();
}

function apply(data, seenEvents, seenAchievements) {
  if (data.source === "none") {
    (data.events || []).forEach((item) => seenEvents.add(item.id));
    (data.achievements || []).forEach((item) => seenAchievements.add(item.id));
    return;
  }
  const total = data.total || 0;
  const quiet = data.source === "report";
  paintSide("morning", data.morning, total, quiet);
  paintSide("evening", data.evening, total, quiet);
  (data.members || []).forEach((member) => {
    document.querySelectorAll(`[data-member="${member.id}"] .avatar`).forEach((avatar) => {
      STATUS.forEach((name) => avatar.classList.remove(name));
      avatar.classList.add(STATUS[member.status] || "is-wait");
    });
  });
  if (quiet) {
    (data.events || []).forEach((item) => seenEvents.add(item.id));
    (data.achievements || []).forEach((item) => seenAchievements.add(item.id));
    if (achievementsChanged(data.achievements || [])) {
      renderAchievements(data.achievements || []);
    }
    return;
  }
  const fresh = (data.events || []).filter((item) => !seenEvents.has(item.id));
  (data.events || []).forEach((item) => seenEvents.add(item.id));
  fresh.forEach((item) => flash(item, data.members || []));
  if (fresh[0]) {
    toast(line(fresh[0]));
  }
  const achievements = data.achievements || [];
  const arrived = achievements.filter((item) => !seenAchievements.has(item.id));
  achievements.forEach((item) => seenAchievements.add(item.id));
  if (arrived.length || achievementsChanged(achievements)) {
    renderAchievements(achievements);
  }
  arrived.forEach((item) => toast(`${item.title} · достижение команды`));
  maybeCelebrate(data.day, "morning", data.morning.count, total);
  maybeCelebrate(data.day, "evening", data.evening.count, total);
}

function paintSide(side, pack, total, quiet = false) {
  const count = pack ? Number(pack.count) || 0 : 0;
  const node = document.querySelector(`[data-odo][data-side="${side}"]`);
  if (node) {
    node.dataset.count = String(count);
    node.dataset.total = String(total);
    node.classList.toggle("is-full", !quiet && Boolean(total) && count === total);
    setOdometer(node, count, total);
  }
  const cap = document.querySelector(`[data-cap="${side}"]`);
  if (cap) {
    const label = side === "morning" ? "утро" : "вечер";
    cap.textContent = quiet ? `${label} · записано ${count} из ${total}` : caption(label, count, total);
  }
  const bar = document.querySelector(`[data-bar="${side}"]`);
  if (!bar) {
    return;
  }
  const full = !quiet && Boolean(total) && count === total;
  bar.classList.toggle("bar--lime", full);
  const fill = bar.querySelector("i");
  if (!fill) {
    return;
  }
  const percent = total ? `${Math.round((1000 * count) / total) / 10}%` : "0%";
  fill.style.setProperty("--v", percent);
  window.setTimeout(() => {
    fill.style.transition = "none";
    fill.style.setProperty("--v", percent);
    fill.style.width = percent;
    window.setTimeout(() => {
      fill.style.transition = "";
      fill.style.width = "";
    }, 40);
  }, BAR_MS);
}

function caption(label, count, total) {
  const missing = Math.max(total - count, 0);
  if (total && count === total) {
    return `${label} · все на связи`;
  }
  if (count === 0) {
    return `${label} · ждём всех`;
  }
  if (missing === 1) {
    return `${label} · ждём одного`;
  }
  if (missing <= 10) {
    return `${label} · ждём ${MISSING[missing]}`;
  }
  return `${label} · ждём ${missing}`;
}

function flash(event, members) {
  const member = members.find((item) => item.short_name === event.member);
  if (!member) {
    return;
  }
  const avatars = [...document.querySelectorAll(`[data-member="${member.id}"] .avatar`)];
  avatars.forEach((avatar) => {
    avatar.classList.remove("is-flash");
    window.setTimeout(() => {
      avatar.classList.add("is-flash");
      window.setTimeout(() => avatar.classList.remove("is-flash"), FLASH_MS);
    }, 40);
  });
  // Искры — из одного аватара, того, что сейчас на экране: иначе их будет несколько пачек.
  const visible = avatars.find((avatar) => {
    const rect = avatar.getBoundingClientRect();
    return rect.width > 0 && rect.bottom > 0 && rect.top < window.innerHeight;
  });
  if (visible) {
    window.setTimeout(() => sparksFrom(visible), 60);
  }
}

function line(event) {
  const verb = event.kind === "evening" ? "итог записан" : "утро записано";
  return `${event.member} · ${verb} · ${event.time}`;
}

function toast(text) {
  document.dispatchEvent(new CustomEvent("nashden:toast", { detail: { text } }));
}

function renderAchievements(items) {
  const box = document.querySelector("[data-achievements]");
  if (!box) {
    return;
  }
  box.replaceChildren();
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    const art = document.querySelector("[data-empty-art]");
    if (art) {
      empty.appendChild(art.content.cloneNode(true));
    }
    const caption = document.createElement("span");
    caption.textContent = "Здесь появятся наши общие достижения — шаги, которые хочется сохранить.";
    empty.appendChild(caption);
    box.appendChild(empty);
    return;
  }
  const note = document.createElement("p");
  note.className = "support-copy support-copy--compact";
  note.textContent = "То, что получилось вместе.";
  box.appendChild(note);
  const stack = document.createElement("div");
  stack.className = "stack";
  stack.style.marginTop = ".5rem";
  stack.style.fontWeight = "600";
  stack.style.fontSize = ".9375rem";
  items.forEach((item) => {
    const row = document.createElement("div");
    row.textContent = item.title;
    stack.appendChild(row);
  });
  box.appendChild(stack);
}

let lastAchievementKey = "";

function achievementsChanged(items) {
  const key = items.map((item) => item.id).join(",");
  if (key === lastAchievementKey) {
    return false;
  }
  lastAchievementKey = key;
  return true;
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
