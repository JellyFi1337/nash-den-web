import { isCalm } from "./motion.js";

// Край ленты гаснет, только если за ним ещё есть содержимое.
// is-start — скрыто слева, is-end — скрыто справа.
const EDGE = 4;

export function initHscroll() {
  const strips = [...document.querySelectorAll(".hscroll")];
  if (!strips.length) {
    return;
  }
  strips.forEach((strip) => {
    let touched = false;
    let placed = false;
    const note = () => {
      touched = true;
      // Плавный доскролл к выбранному дню не должен спорить с жестом.
      const left = strip.scrollLeft;
      strip.scrollLeft = left;
    };
    strip.addEventListener("pointerdown", note, { passive: true });
    strip.addEventListener("wheel", note, { passive: true });
    strip.addEventListener("scroll", () => mark(strip), { passive: true });
    if ("ResizeObserver" in window) {
      const observer = new ResizeObserver(() => mark(strip));
      observer.observe(strip);
    }
    const place = () => {
      if (!touched && !placed) {
        placed = center(strip);
      }
      mark(strip);
    };
    window.requestAnimationFrame(place);
    // Кадры в скрытой вкладке могут не прийти: вторая попытка по таймеру.
    window.setTimeout(place, 400);
  });
  window.addEventListener("resize", () => strips.forEach(mark));
}

function mark(strip) {
  const max = Math.max(strip.scrollWidth - strip.clientWidth, 0);
  strip.classList.toggle("is-start", strip.scrollLeft > EDGE);
  strip.classList.toggle("is-end", max - strip.scrollLeft > EDGE);
}

function center(strip) {
  const current = strip.querySelector('[aria-current="date"]');
  if (!current) {
    return true;
  }
  if (strip.clientWidth < 1) {
    return false;
  }
  const host = strip.getBoundingClientRect();
  const rect = current.getBoundingClientRect();
  const elementLeft = rect.left - host.left + strip.scrollLeft;
  const target = elementLeft - (strip.clientWidth - rect.width) / 2;
  const max = Math.max(strip.scrollWidth - strip.clientWidth, 0);
  const left = Math.min(Math.max(target, 0), max);
  if (Math.abs(strip.scrollLeft - left) < 1) {
    return true;
  }
  if (isCalm()) {
    strip.scrollLeft = left;
    return true;
  }
  strip.scrollTo({ left, behavior: "smooth" });
  return true;
}
