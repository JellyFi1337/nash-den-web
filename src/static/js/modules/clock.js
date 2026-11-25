import { createRoll } from "./roll.js";
import { motionBoot, serverNow, zonedHour } from "./time.js";

// Живые часы: до смены кода (data-countdown="rollover") и до конца потока ("end").
// Тик выровнен по началу секунды сервера, во фоновой вкладке не идёт.
const DAY = 24 * 60 * 60 * 1000;

export function initClocks() {
  const boot = motionBoot();
  const nodes = [...document.querySelectorAll("[data-countdown]")];
  if (!boot || !nodes.length) {
    return;
  }
  let rollover = Number(boot.rollover);
  let dayStart = Number(boot.day_start);
  const items = nodes
    .map((node) => {
      const digits = node.querySelector("[data-roll]");
      if (!digits) {
        return null;
      }
      return {
        node,
        kind: node.dataset.countdown,
        set: createRoll(digits, "dd:dd:dd"),
        days: node.querySelector("[data-days]"),
        label: node.querySelector("[data-countdown-label]"),
        bar: node.querySelector("[data-countdown-progress]"),
        spoken: node.querySelector("[data-countdown-sr]"),
        minute: -1,
      };
    })
    .filter(Boolean);
  let timer = 0;
  let started = false;

  const tick = () => {
    const now = serverNow(boot);
    if (now >= rollover) {
      while (now >= rollover) {
        dayStart = rollover;
        rollover += DAY;
      }
      if (started) {
        say("Код дня сменился. Новый — в личке бота");
      }
    }
    items.forEach((item) => {
      if (item.kind === "end") {
        paintEnd(item, now, boot);
      } else {
        paintCode(item, now, boot, rollover, dayStart);
      }
    });
    started = true;
  };

  const loop = () => {
    window.clearTimeout(timer);
    tick();
    const wait = 1000 - (serverNow(boot) % 1000) + 15;
    timer = window.setTimeout(loop, wait);
  };

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      window.clearTimeout(timer);
    } else {
      loop();
    }
  });
  loop();
}

function paintCode(item, now, boot, rollover, dayStart) {
  const left = Math.max(rollover - now, 0);
  const night = zonedHour(boot, now) < Number(boot.split);
  const label = night ? "новый код через" : "код действует ещё";
  if (item.label && item.label.textContent !== label) {
    item.label.textContent = label;
  }
  item.set(clock(left));
  if (item.bar) {
    const share = Math.min(Math.max((now - dayStart) / (rollover - dayStart), 0), 1);
    item.bar.style.setProperty("--p", `${(share * 100).toFixed(2)}%`);
  }
  speak(item, left, `${label} ${spoken(left)}`);
}

function paintEnd(item, now, boot) {
  const end = Number(boot.end);
  if (!end || end <= now) {
    item.node.hidden = true;
    return;
  }
  const left = end - now;
  const days = Math.floor(left / DAY);
  if (item.days && item.days.textContent !== String(days)) {
    item.days.textContent = String(days);
  }
  item.set(clock(left % DAY));
  speak(item, left, `до конца потока ${days} ${plural(days)} ${spoken(left % DAY)}`);
}

function speak(item, left, text) {
  const minute = Math.floor(left / 60000);
  if (!item.spoken || minute === item.minute) {
    return;
  }
  item.minute = minute;
  item.spoken.textContent = text;
}

function clock(ms) {
  const total = Math.floor(ms / 1000);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  return [hours, minutes, seconds].map((value) => String(value).padStart(2, "0")).join("");
}

function spoken(ms) {
  const total = Math.floor(ms / 60000);
  const hours = Math.floor(total / 60);
  const minutes = total % 60;
  return hours ? `${hours} ч ${minutes} мин` : `${minutes} мин`;
}

function plural(count) {
  const tail = count % 100;
  const last = count % 10;
  if (tail >= 11 && tail <= 14) {
    return "дней";
  }
  if (last === 1) {
    return "день";
  }
  if (last >= 2 && last <= 4) {
    return "дня";
  }
  return "дней";
}

function say(text) {
  document.dispatchEvent(new CustomEvent("nashden:toast", { detail: { text } }));
}
