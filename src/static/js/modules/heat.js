// Подсказка в «ритме команды»: кто, какой день и что было. Мышь — наведением, телефон — касанием.
// Кнопки дат графика дают ту же подсказку клавиатурой и касанием, с большой областью нажатия.
const GAP = 8;

export function initHeatTips() {
  document.querySelectorAll(".heat, .chart-panel").forEach((heat) => {
    const host = heat.closest(".card") || heat.parentElement;
    if (!host || !heat.querySelector("[data-tip]")) {
      return;
    }
    const tip = document.createElement("div");
    tip.className = "heat-tip";
    tip.setAttribute("aria-hidden", "true");
    host.appendChild(tip);
    let active = null;

    const hide = () => {
      tip.classList.remove("is-on");
      if (active) {
        active.classList.remove("is-active");
        active = null;
      }
      heat.querySelectorAll(".chart__point.is-active").forEach((point) => point.classList.remove("is-active"));
    };

    const show = (cell) => {
      if (!cell || !cell.dataset.tip) {
        hide();
        return;
      }
      if (active && active !== cell) {
        active.classList.remove("is-active");
      }
      active = cell;
      cell.classList.add("is-active");
      heat.querySelectorAll(".chart__point").forEach((point) => point.classList.toggle(
        "is-active", point.dataset.point === cell.dataset.point,
      ));
      tip.textContent = cell.dataset.tip;
      tip.classList.add("is-on");
      // После смены ширины старый left сжимает абсолютную подсказку до одного слова.
      tip.style.left = `${GAP}px`;
      const box = host.getBoundingClientRect();
      const point = cell.dataset.point && heat.querySelector(`.chart__point[data-point="${cell.dataset.point}"]`);
      const rect = (point || cell).getBoundingClientRect();
      const width = tip.offsetWidth;
      const height = tip.offsetHeight;
      const left = Math.min(
        Math.max(rect.left - box.left + rect.width / 2 - width / 2, GAP),
        box.width - width - GAP,
      );
      let top = rect.top - box.top - height - GAP;
      if (top < GAP) {
        top = rect.bottom - box.top + GAP;
      }
      tip.style.left = `${Math.round(left)}px`;
      tip.style.top = `${Math.round(top)}px`;
    };

    const cellOf = (event) =>
      event.target instanceof Element ? event.target.closest("[data-tip]") : null;

    heat.addEventListener("pointerover", (event) => {
      if (event.pointerType !== "touch") {
        show(cellOf(event));
      }
    });
    heat.addEventListener("pointerleave", (event) => {
      if (event.pointerType !== "touch") {
        if (!heat.contains(document.activeElement)) hide();
      }
    });
    heat.addEventListener("pointerdown", (event) => {
      if (event.pointerType === "touch") {
        const cell = cellOf(event);
        if (heat.matches(".chart-panel") && !cell?.matches("button")) return;
        if (cell && cell === active) {
          hide();
        } else {
          show(cell);
        }
      }
    });
    heat.addEventListener("focusin", (event) => show(cellOf(event)));
    heat.addEventListener("click", (event) => {
      const cell = cellOf(event);
      if (cell?.matches(".chart__date")) show(cell);
    });
    heat.addEventListener("focusout", (event) => {
      if (!heat.contains(event.relatedTarget)) hide();
    });
    heat.addEventListener("keydown", (event) => {
      if (event.key === "Escape") hide();
    });
    document.addEventListener("pointerdown", (event) => {
      if (event.target instanceof Node && !heat.contains(event.target)) {
        hide();
      }
    });
    window.addEventListener("scroll", hide, { passive: true });
  });
}
