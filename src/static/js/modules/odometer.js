import { isCalm } from "./motion.js";

const FALLBACK_MS = 700;
const START_MS = 40;

export function initOdometer(root = document) {
  root.querySelectorAll("[data-odo]").forEach((el) => {
    setOdometer(el, el.dataset.count || "0", el.dataset.total || "0");
  });
}

export function setOdometer(el, count, total) {
  const reduced = isCalm();
  const digits = padded(count);
  const columns = ensure(el, digits.length, total);
  digits.split("").forEach((digit, index) => {
    move(columns[index], digit, reduced);
  });
  const tail = el.querySelector("[data-odo-tail]");
  if (tail) {
    tail.textContent = `/${total}`;
  }
  el.setAttribute("role", "img");
  el.setAttribute("aria-label", spoken(el, count, total));
}

function spoken(el, count, total) {
  const names = { morning: "утро", evening: "вечер" };
  const side = names[el.dataset.side] || "число";
  return `${side}: ${count} из ${total}`;
}

function padded(count) {
  // Без нуля слева: пустое утро — «0», а не «00», когда в команде больше девяти человек.
  return String(count);
}

function ensure(el, length, total) {
  const ready = el.querySelectorAll(".odo");
  if (ready.length === length && el.querySelector("[data-odo-tail]")) {
    return ready;
  }
  el.textContent = "";
  const columns = [];
  for (let index = 0; index < length; index += 1) {
    const column = document.createElement("span");
    column.className = "odo";
    column.setAttribute("aria-hidden", "true");
    for (let digit = 0; digit <= 9; digit += 1) {
      const cell = document.createElement("span");
      cell.textContent = String(digit);
      column.appendChild(cell);
    }
    el.appendChild(column);
    columns.push(column);
  }
  const tail = document.createElement("span");
  tail.dataset.odoTail = "1";
  tail.setAttribute("aria-hidden", "true");
  tail.textContent = `/${total}`;
  el.appendChild(tail);
  return columns;
}

function move(column, digit, reduced) {
  column.style.width = `${measure(column, digit)}px`;
  const shift = `translateY(${-Number(digit)}em)`;
  const apply = () => {
    column.querySelectorAll("span").forEach((cell) => {
      if (reduced) {
        cell.style.transition = "none";
      }
      cell.style.transform = shift;
    });
  };
  if (reduced) {
    apply();
  } else {
    window.setTimeout(apply, START_MS);
  }
  window.setTimeout(() => {
    column.querySelectorAll("span").forEach((cell) => {
      cell.style.transition = "none";
      cell.style.transform = shift;
    });
    window.setTimeout(() => {
      column.querySelectorAll("span").forEach((cell) => {
        cell.style.transition = "";
      });
    }, START_MS);
  }, FALLBACK_MS);
}

function measure(column, digit) {
  const probe = document.createElement("span");
  probe.textContent = digit;
  probe.style.cssText = "position:absolute;visibility:hidden";
  column.appendChild(probe);
  const width = Math.ceil(probe.getBoundingClientRect().width) + 1;
  probe.remove();
  return width;
}
