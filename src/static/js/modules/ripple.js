let skipRequested = false;

export function resetRippleSkip() {
  skipRequested = false;
}

export function requestRippleSkip() {
  skipRequested = true;
}

export function isRippleSkipped() {
  return skipRequested;
}

export function ripple(root, milliseconds, from, useFilter = true) {
  return new Promise((resolve) => {
    const displacement = document.getElementById("disp");
    const turbulence = document.getElementById("turb");
    const scan = document.querySelector("[data-scanlines]");
    let finished = false;
    const finish = () => {
      if (finished) {
        return;
      }
      finished = true;
      if (displacement) {
        displacement.setAttribute("scale", "0");
      }
      if (root) {
        root.style.filter = "";
      }
      if (scan) {
        scan.classList.remove("is-on");
      }
      resolve();
    };
    if (!root) {
      finish();
      return;
    }
    if (scan) {
      scan.classList.add("is-on");
    }
    if (useFilter && displacement && turbulence) {
      root.style.filter = "url(#rip)";
    }
    resetRippleSkip();
    const started = performance.now();
    let lastSeed = 0;
    let seed = 1;
    // Кадр может не прийти в фоновой вкладке: таймер всё равно снимает фильтр.
    window.setTimeout(finish, milliseconds + 200);
    const step = (frame) => {
      if (finished) {
        return;
      }
      const progress = Math.min((frame - started) / milliseconds, 1);
      if (progress >= 1 || skipRequested) {
        finish();
        return;
      }
      if (useFilter && displacement && turbulence && frame - lastSeed > 55) {
        lastSeed = frame;
        seed = (seed % 40) + 1;
        turbulence.setAttribute("seed", String(seed));
        const frequencyX = (0.003 + Math.random() * 0.006).toFixed(4);
        const frequencyY = (0.05 + 0.12 * (1 - progress)).toFixed(3);
        turbulence.setAttribute("baseFrequency", `${frequencyX} ${frequencyY}`);
        const jerk = Math.random() < 0.18 ? 1.8 : 1;
        const scale = (from * (1 - progress) ** 1.6 * jerk).toFixed(1);
        displacement.setAttribute("scale", scale);
      }
      window.requestAnimationFrame(step);
    };
    step(started);
  });
}
