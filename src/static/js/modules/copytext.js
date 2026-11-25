// Кнопка «Скопировать» у текста для общего чата.
// Буфер обмена есть только в защищённом контексте (HTTPS или localhost); сайт сейчас открыт
// по HTTP, поэтому запасной путь обязателен: выделить текст и подсказать, как его скопировать.

const COPIED = "Текст скопирован";
const SELECTED = "Текст выделен — скопируйте его: Ctrl+C или «Копировать» в меню";

export function initCopyText() {
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-copy]");
    if (!button) {
      return;
    }
    const source = document.getElementById(button.dataset.copy || "");
    if (!source) {
      return;
    }
    copy(source);
  });
}

async function copy(source) {
  const text = source.textContent || "";
  if (window.isSecureContext && navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      toast(COPIED);
      return;
    } catch (error) {
      // Отказ браузера — переходим к выделению ниже.
    }
  }
  select(source);
  toast(legacyCopy() ? COPIED : SELECTED);
}

function select(node) {
  const selection = window.getSelection();
  if (!selection) {
    return;
  }
  const range = document.createRange();
  range.selectNodeContents(node);
  selection.removeAllRanges();
  selection.addRange(range);
  node.focus({ preventScroll: true });
}

function legacyCopy() {
  // Устаревший путь, но на HTTP у части браузеров это единственная работающая копия.
  try {
    return typeof document.execCommand === "function" && document.execCommand("copy");
  } catch (error) {
    return false;
  }
}

function toast(text) {
  document.dispatchEvent(new CustomEvent("nashden:toast", { detail: { text } }));
}
