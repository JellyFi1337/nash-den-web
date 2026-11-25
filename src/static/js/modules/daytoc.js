import { isCalm } from "./motion.js";

export function initDayToc() {
  const toc = document.querySelector("[data-toc]");
  if (!toc) return;
  const root = toc.closest("[data-swipe]");
  const sentinel = root.querySelector(".toc-sentinel");
  const links = [...toc.querySelectorAll('a[href^="#"]')];
  const sections = links.map((link) => document.getElementById(link.hash.slice(1)));
  if (sections.some((section) => !section)) return;
  let height = 0;
  let observer;
  let active = links[0];

  function select(link) {
    links.forEach((item) => {
      if (item === link) item.setAttribute("aria-current", "true");
      else item.removeAttribute("aria-current");
    });
    active = link;
    const host = toc.getBoundingClientRect();
    const rect = link.getBoundingClientRect();
    const padding = 12;
    let left = toc.scrollLeft;
    if (rect.left < host.left + padding) left += rect.left - host.left - padding;
    else if (rect.right > host.right - padding) left += rect.right - host.right + padding;
    const max = Math.max(0, toc.scrollWidth - toc.clientWidth);
    toc.scrollTo({ left: Math.max(0, Math.min(left, max)), behavior: isCalm() ? "instant" : "smooth" });
  }

  function markCurrent() {
    // На компьютере соседние карточки имеют одинаковый верх: сохраняем выбранную
    // плашку в этом ряду, а при входе в новый ряд выбираем его первый блок.
    const tops = sections.map((section) => section.getBoundingClientRect().top);
    const passed = tops.filter((top) => top <= height + 24);
    let top = passed.length ? Math.max(...passed) : tops[0];
    if (window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2) {
      top = tops.at(-1);
    }
    const row = links.filter((link, index) => Math.abs(tops[index] - top) < 2);
    const next = row.includes(active) ? active : row[0];
    if (next && next !== active) select(next);
  }

  function measure() {
    const nextHeight = Math.ceil(toc.getBoundingClientRect().height);
    height = nextHeight;
    root.style.setProperty("--day-toc-height", `${height}px`);
    if ("IntersectionObserver" in window) {
      observer?.disconnect();
      observer = new IntersectionObserver(markCurrent, {
        // Узкая полоса под оглавлением даёт событие и для очень длинного блока.
        rootMargin: `-${height + 24}px 0px -${Math.max(0, window.innerHeight - height - 25)}px 0px`, threshold: 0,
      });
      sections.forEach((section) => observer.observe(section));
    }
    markCurrent();
  }

  if ("IntersectionObserver" in window) {
    const stuck = new IntersectionObserver(([entry]) => {
      toc.classList.toggle("is-stuck", !entry.isIntersecting && entry.boundingClientRect.top < 0);
    });
    stuck.observe(sentinel);
  } else {
    window.addEventListener("scroll", () => {
      toc.classList.toggle("is-stuck", sentinel.getBoundingClientRect().top < 0);
      markCurrent();
    }, { passive: true });
  }
  links.forEach((link, index) => link.addEventListener("click", (event) => {
    if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
    event.preventDefault();
    select(link);
    history.pushState(null, "", link.hash);
    sections[index].scrollIntoView({ block: "start", behavior: isCalm() ? "instant" : "smooth" });
  }));
  if ("ResizeObserver" in window) new ResizeObserver(measure).observe(toc);
  window.addEventListener("resize", measure);
  document.fonts?.ready.then(measure);
  measure();
}
