import { isCalm } from "./motion.js";

// Цифры-барабаны: каждая цифра — отдельная лента 0…9 и ещё один 0 в конце.
// 9 → 0 крутится вперёд через нижний 0 и незаметно встаёт наверх,
// 0 → 9 (обратный отсчёт) — назад на одну позицию, а не через всю ленту.
const SETTLE_MS = 620;

export function createRoll(el, pattern) {
  el.textContent = "";
  el.classList.add("roll");
  const columns = [];
  for (const char of pattern) {
    if (char !== "d") {
      const sep = document.createElement("span");
      sep.className = "roll__sep";
      sep.textContent = char;
      el.appendChild(sep);
      continue;
    }
    const win = document.createElement("span");
    win.className = "roll__win";
    const strip = document.createElement("span");
    strip.className = "roll__strip";
    for (let digit = 0; digit <= 10; digit += 1) {
      const cell = document.createElement("span");
      cell.textContent = String(digit % 10);
      strip.appendChild(cell);
    }
    win.appendChild(strip);
    el.appendChild(win);
    columns.push({ win, strip, value: -1, timer: 0 });
  }
  return (digits, { hideLeadingZero = false } = {}) => {
    [...digits].forEach((char, index) => {
      const column = columns[index];
      if (!column) {
        return;
      }
      const value = Number(char);
      if (index === 0) {
        column.win.classList.toggle("is-hidden", hideLeadingZero && value === 0);
      }
      if (column.value === value) {
        return;
      }
      window.clearTimeout(column.timer);
      const from = column.value;
      column.value = value;
      if (from < 0 || isCalm() || document.hidden) {
        snap(column.strip, value);
      } else if (from === 9 && value === 0) {
        column.strip.style.transform = "translateY(-10em)";
        column.timer = window.setTimeout(() => snap(column.strip, 0), SETTLE_MS);
      } else if (from === 0 && value === 9) {
        snap(column.strip, 10);
        window.requestAnimationFrame(() => {
          column.strip.style.transform = "translateY(-9em)";
        });
      } else {
        column.strip.style.transform = `translateY(${-value}em)`;
      }
    });
  };
}

function snap(strip, position) {
  strip.style.transition = "none";
  strip.style.transform = `translateY(${-position}em)`;
  void strip.offsetHeight;
  strip.style.transition = "";
}
