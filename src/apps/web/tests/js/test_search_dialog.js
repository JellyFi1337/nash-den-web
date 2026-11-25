import { initSearch } from "../modules/search.js";

// Внешний модуль для изолированной страницы проверки: настоящий dialog и поле поиска.
initSearch();
const dialog = document.getElementById("search-dialog");
const input = document.getElementById("search-query");
const trigger = document.querySelector("[data-search-open]");
let checks = 0;
function check(condition, description) {
  if (!condition) throw new Error(description);
  checks += 1;
}
function key(target, value, modifiers = {}) {
  const event = new KeyboardEvent("keydown", { key: value, bubbles: true, cancelable: true, ...modifiers });
  target.dispatchEvent(event);
  return event;
}

trigger.click();
check(dialog.open && document.activeElement === input, "Лупа открывает окно и поле получает фокус");
input.value = "заполненный запрос";
const closed = new Promise((resolve) => dialog.addEventListener("close", resolve, { once: true }));
const escape = key(input, "Escape");
check(!dialog.open && escape.defaultPrevented, "Esc закрывает окно с заполненным полем");
check(input.value === "заполненный запрос", "Esc не теряется на очистке type=search");
await closed;
check(document.activeElement === trigger, "После закрытия фокус возвращается на лупу");

for (const [value, modifiers] of [["k", { ctrlKey: true }], ["k", { metaKey: true }], ["/", {}]]) {
  input.value = "";
  key(document, value, modifiers);
  check(dialog.open, `Сочетание ${value} открывает поиск`);
  const slash = key(input, "/");
  check(!slash.defaultPrevented && dialog.open, "Клавиша / в поле не перехватывается");
  if (window.innerWidth < 640) {
    check(Math.abs(dialog.getBoundingClientRect().width - window.innerWidth) < 1,
      "Мобильное окно занимает всю ширину, без второго поля прокрутки");
  }
  const closed = new Promise((resolve) => dialog.addEventListener("close", resolve, { once: true }));
  key(input, "Escape");
  await closed;
}
trigger.click();
input.value = "повторный запрос";
key(input, "Enter");
check(document.getElementById("search-status").textContent === "Ищем…", "Enter повторяет поиск без результатов");
key(input, "Escape");
check(!dialog.open, "Закрытие отменяет отложенный повторный поиск");
document.getElementById("test-results").textContent = `${checks} проверок поиска прошли`;
