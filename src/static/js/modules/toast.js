const VISIBLE_MS = 2600;
const MIN_MS = 1600;
const MAX_WAITING = 3;

export function initToast() {
  const node = document.querySelector(".toast");
  if (!node) {
    return;
  }
  const queue = [];
  let active = null;

  const finish = () => {
    active = null;
    if (queue.length) {
      showNext();
      return;
    }
    node.classList.remove("is-on");
  };

  const showNext = () => {
    if (active || !queue.length) {
      return;
    }
    active = queue.shift();
    node.textContent = active.text;
    node.classList.add("is-on");
    const wait = Math.max(active.ms || VISIBLE_MS, MIN_MS);
    window.setTimeout(finish, wait);
  };

  document.addEventListener("nashden:toast", (event) => {
    const detail = event.detail || {};
    const text = detail.text || "";
    const last = queue[queue.length - 1];
    const tail = last ? last.text : active && active.text;
    if (tail && tail === text) {
      return;
    }
    if (queue.length >= MAX_WAITING) {
      queue.shift();
    }
    queue.push({ text, ms: detail.ms });
    showNext();
  });
}
