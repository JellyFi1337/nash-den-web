const HISTORY_KEY = "nd-search-history";
const DELAY = 180;

export function initSearch() {
  const trigger = document.querySelector("[data-search-open]");
  const dialog = document.getElementById("search-dialog");
  if (!trigger || !dialog) return;
  const input = dialog.querySelector("input");
  const results = dialog.querySelector("[data-search-results]");
  const historyBox = dialog.querySelector("[data-search-history]");
  const status = dialog.querySelector("[role='status']");
  let history = readHistory();
  let timer;
  let controller;
  let generation = 0;
  let selected = -1;
  let links = [];
  let opener = trigger;

  trigger.addEventListener("click", open);
  dialog.querySelector("[data-search-close]").addEventListener("click", close);
  dialog.addEventListener("cancel", cancel);
  dialog.addEventListener("close", () => {
    if (dialog.open) return;
    cancel();
    opener?.focus({ preventScroll: true });
  });
  dialog.addEventListener("click", (event) => {
    if (event.target !== dialog) return;
    const rect = dialog.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) close();
  });
  document.addEventListener("keydown", (event) => {
    const typing = event.target instanceof Element && event.target.closest("input, textarea, select, [contenteditable]:not([contenteditable='false'])");
    const shortcut = ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") || (event.key === "/" && !event.ctrlKey && !event.metaKey && !event.altKey);
    if (shortcut && !typing && !document.querySelector("dialog[open]")) {
      event.preventDefault();
      open();
    }
  });
  input.addEventListener("input", schedule);
  dialog.addEventListener("keydown", (event) => {
    // Поле type=search иначе может забрать Esc себе и только очистить запрос.
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      close();
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      if (!links.length) return;
      event.preventDefault();
      selected = selected < 0 ? (event.key === "ArrowDown" ? 0 : links.length - 1) : (selected + (event.key === "ArrowDown" ? 1 : -1) + links.length) % links.length;
      links.forEach((link, index) => link.classList.toggle("is-selected", index === selected));
      links[selected].focus({ preventScroll: true });
      links[selected].scrollIntoView({ block: "nearest", behavior: "instant" });
    } else if (event.key === "Enter" && event.target === input) {
      event.preventDefault();
      if (links.length) links[Math.max(selected, 0)].click();
      else schedule();
    }
  });

  function open() {
    opener = document.activeElement === document.body ? trigger : document.activeElement;
    cancel();
    dialog.showModal();
    input.focus();
    drawHistory();
    if (input.value.trim().length >= 2) schedule();
  }

  function close() {
    cancel();
    dialog.close();
  }

  function cancel() {
    window.clearTimeout(timer);
    controller?.abort();
    generation += 1;
    results.removeAttribute("aria-busy");
  }

  function schedule() {
    cancel();
    results.replaceChildren();
    links = [];
    selected = -1;
    const query = input.value.trim();
    historyBox.hidden = query.length >= 2;
    if (query.length < 2) {
      status.textContent = "Введите хотя бы два символа.";
      return;
    }
    status.textContent = "Ищем…";
    const expected = generation;
    timer = window.setTimeout(() => search(query, expected), DELAY);
  }

  async function search(query, expected) {
    if (expected !== generation || !dialog.open) return;
    controller = new AbortController();
    results.setAttribute("aria-busy", "true");
    try {
      const url = new URL(dialog.dataset.searchUrl, window.location.origin);
      url.searchParams.set("q", query);
      const response = await fetch(url, { headers: { Accept: "application/json" }, credentials: "same-origin", cache: "no-store", signal: controller.signal });
      if (expected !== generation || !dialog.open) return;
      if (response.status === 401) {
        status.textContent = "Новый день — войдите снова.";
        const enter = document.createElement("a");
        enter.className = "chip week-link";
        enter.href = "/enter/";
        enter.textContent = "Войти";
        results.append(enter);
        return;
      }
      if (!response.ok) throw new Error("search");
      const data = await response.json();
      if (expected !== generation || !dialog.open) return;
      drawResults(data.results);
      status.textContent = data.results.length ? `Найдено: ${data.results.length}` : "Ничего не нашлось. Попробуйте другое слово.";
      remember(query);
    } catch (error) {
      if (error.name !== "AbortError" && expected === generation && dialog.open) status.textContent = "Ошибка сети. Попробуйте ещё раз.";
    } finally {
      if (expected === generation) results.removeAttribute("aria-busy");
    }
  }

  function drawResults(rows) {
    const days = new Map();
    for (const row of rows) {
      if (!days.has(row.date)) days.set(row.date, []);
      days.get(row.date).push(row);
    }
    for (const group of days.values()) {
      const heading = document.createElement("h3");
      heading.className = "label search-date";
      heading.textContent = group[0].label;
      results.append(heading);
      for (const row of group) {
        const link = document.createElement("a");
        link.className = "search-result";
        link.href = row.url;
        const block = document.createElement("span");
        block.className = "label";
        block.textContent = row.block;
        const snippet = document.createElement("span");
        // Селектор экранирует весь текст и добавляет только mark.hl.
        snippet.innerHTML = row.snippet;
        link.append(block, snippet);
        link.addEventListener("focus", () => {
          selected = links.indexOf(link);
          links.forEach((item, index) => item.classList.toggle("is-selected", index === selected));
        });
        results.append(link);
        links.push(link);
      }
    }
  }

  function remember(query) {
    history = [query, ...history.filter((item) => item !== query)].slice(0, 5);
    try { localStorage.setItem(HISTORY_KEY, JSON.stringify(history)); } catch (error) { /* Поиск работает и без хранилища. */ }
    drawHistory();
  }

  function drawHistory() {
    historyBox.replaceChildren();
    for (const query of history) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "chip search-recent";
      button.textContent = query;
      button.addEventListener("click", () => { input.value = query; input.focus(); schedule(); });
      historyBox.append(button);
    }
    historyBox.hidden = input.value.trim().length >= 2;
  }
}

function readHistory() {
  try {
    const value = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
    return Array.isArray(value) ? value.filter((item) => typeof item === "string" && item.trim().length >= 2 && item.length <= 80).slice(0, 5) : [];
  } catch (error) { return []; }
}
