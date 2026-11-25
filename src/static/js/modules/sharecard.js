const WIDTH = 1080;
const HEIGHT = 1350;
const PAD = 80;

export function initSharecard() {
  const trigger = document.querySelector("[data-sharecard]");
  const node = document.getElementById("sharecard-data");
  const dialog = document.getElementById("sharecard-dialog");
  if (!trigger || !node || !dialog || !dialog.showModal) return;
  let data;
  try { data = JSON.parse(node.textContent); } catch { return; }
  const image = dialog.querySelector("[data-sharecard-preview]");
  const status = dialog.querySelector("[data-sharecard-status]");
  const save = dialog.querySelector("[data-sharecard-save]");
  const share = dialog.querySelector("[data-sharecard-share]");
  let generation = 0;
  let blob;
  let file;

  dialog.querySelector("[data-sharecard-close]").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => {
    generation += 1;
    trigger.focus({ preventScroll: true });
  });
  trigger.addEventListener("click", async () => {
    const current = ++generation;
    dialog.showModal();
    dialog.setAttribute("aria-busy", "true");
    status.textContent = "Готовим карточку…";
    status.hidden = false;
    save.disabled = true;
    share.hidden = true;
    image.hidden = true;
    try {
      const canvas = await renderSharecard(data, trigger.dataset.sharecardMark);
      const generated = await toBlob(canvas);
      if (current !== generation || !dialog.open) return;
      blob = generated;
      file = null;
      image.src = canvas.toDataURL("image/png");
      image.alt = `${data.quote}${data.author ? ` — ${data.author}` : ""} · ${data.date} · ${data.caption}`;
      image.hidden = false;
      save.disabled = false;
      status.hidden = true;
      // На HTTP остаётся скачивание; наличие API само по себе не означает поддержку файлов.
      if (window.isSecureContext && location.protocol === "https:" && navigator.share && typeof File !== "undefined") {
        const candidate = new File([blob], data.filename, { type: "image/png" });
        try {
          if (navigator.canShare?.({ files: [candidate] })) {
            file = candidate;
            share.hidden = false;
          }
        } catch { /* Скачивание остаётся доступно при отказе проверки возможностей. */ }
      }
    } catch {
      if (current === generation && dialog.open) {
        status.textContent = "Не удалось подготовить карточку. Закройте окно и попробуйте ещё раз.";
      }
    } finally {
      if (current === generation) dialog.removeAttribute("aria-busy");
    }
  });
  save.addEventListener("click", () => {
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = data.filename;
    link.hidden = true;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 5000);
  });
  share.addEventListener("click", async () => {
    if (!file) return;
    try { await navigator.share({ files: [file] }); }
    catch (error) {
      if (error.name !== "AbortError") {
        status.textContent = "Не удалось поделиться. Сохраните карточку.";
        status.hidden = false;
      }
    }
  });
}

export async function renderSharecard(data, markUrl) {
  const style = getComputedStyle(document.documentElement);
  const display = style.getPropertyValue("--font-display").trim();
  const mono = style.getPropertyValue("--font-mono").trim();
  const loaded = await within(Promise.all([
    document.fonts.load(`900 96px ${display}`, data.quote),
    document.fonts.load(`700 38px ${display}`, data.author || data.caption),
    document.fonts.load(`700 26px ${mono}`, data.date + data.caption),
  ]));
  if (loaded.some((fonts) => !fonts.length)) throw new Error("Шрифт карточки не загружен");
  const mark = await within(new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = reject;
    image.src = markUrl;
  }));
  const canvas = document.createElement("canvas");
  canvas.width = WIDTH;
  canvas.height = HEIGHT;
  const ctx = canvas.getContext("2d");
  // В яркой палитре тёплая заливка совпадает с цветом знака: берём фон страницы.
  const vivid = document.documentElement.dataset.palette === "vivid";
  const textColor = style.getPropertyValue(vivid ? "--fg" : "--ink").trim();
  ctx.fillStyle = style.getPropertyValue(vivid ? "--page" : "--hot-fill").trim();
  ctx.fillRect(0, 0, WIDTH, HEIGHT);
  // SVG берётся как готовая картинка: формы, цвет и горизонт знака не меняются.
  ctx.drawImage(mark, PAD, 70, 128, 128);
  ctx.fillStyle = textColor;
  ctx.textBaseline = "top";
  ctx.font = `700 26px ${mono}`;
  ctx.fillText("цитата дня", PAD, 275);
  const areaHeight = data.author ? 660 : 785;
  const quote = fitText(ctx, data.quote, WIDTH - PAD * 2, areaHeight, 900, display, 100);
  drawLines(ctx, quote, PAD, 325 + (areaHeight - quote.lines.length * quote.size * 1.08) / 2);
  if (data.author) {
    const author = fitText(ctx, data.author, WIDTH - PAD * 2, 125, 700, display, 38);
    drawLines(ctx, author, PAD, 1035);
  }
  ctx.fillStyle = style.getPropertyValue(vivid ? "--surface-edge" : "--hot-edge").trim();
  ctx.fillRect(PAD, 1176, WIDTH - PAD * 2, 2);
  ctx.fillStyle = textColor;
  ctx.font = `700 26px ${mono}`;
  ctx.fillText(data.date, PAD, 1210);
  const caption = fitText(ctx, data.caption, WIDTH - PAD * 2, 60, 700, mono, 26);
  drawLines(ctx, caption, PAD, 1255);
  return canvas;
}

export function wrapText(ctx, text, width) {
  const lines = [];
  for (const paragraph of String(text).split(/\r?\n/)) {
    let line = "";
    for (const word of paragraph.trim().split(/[ \t]+/)) {
      if (!word) continue;
      if (ctx.measureText(word).width > width) {
        if (line) lines.push(line);
        line = "";
        const pieces = typeof Intl.Segmenter === "function"
          ? [...new Intl.Segmenter("ru", { granularity: "grapheme" }).segment(word)].map((part) => part.segment)
          : [...word];
        for (const part of pieces) {
          if (line && ctx.measureText(line + part).width > width) {
            lines.push(line);
            line = "";
          }
          line += part;
        }
      } else {
        const next = line ? `${line} ${word}` : word;
        if (line && ctx.measureText(next).width > width) {
          lines.push(line);
          line = word;
        } else line = next;
      }
    }
    lines.push(line);
  }
  return lines;
}

function fitText(ctx, text, width, height, weight, family, maximum) {
  for (let size = maximum; size >= 14; size -= 2) {
    ctx.font = `${weight} ${size}px ${family}`;
    const lines = wrapText(ctx, text, width);
    if (lines.length * size * 1.08 <= height) return { lines, size, font: ctx.font };
  }
  throw new Error("Текст не помещается в карточку");
}

function drawLines(ctx, block, x, y) {
  ctx.font = block.font;
  block.lines.forEach((line, index) => ctx.fillText(line, x, y + index * block.size * 1.08));
}

function toBlob(canvas) {
  return new Promise((resolve, reject) => canvas.toBlob((blob) => {
    if (blob) resolve(blob);
    else reject(new Error("PNG не создан"));
  }, "image/png"));
}

function within(promise) {
  let timer;
  return Promise.race([
    promise,
    new Promise((_, reject) => { timer = window.setTimeout(() => reject(new Error("Ожидание карточки истекло")), 15000); }),
  ]).finally(() => window.clearTimeout(timer));
}
