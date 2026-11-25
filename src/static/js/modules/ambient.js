import { isCalm, onCalmChange } from "./motion.js";
import { getPref, onPrefs } from "./prefs.js";
import { motionBoot, serverNow, zonedHour } from "./time.js";

// Живой фон за карточками. Сцена — по времени суток в Москве или выбранная в меню:
// утро — лучи рассвета, пылинки в них и вспышки света; день — тонкие потоки в три слоя,
// по которым бегут сигналы-кометы; вечер — тёплые волны с шёлковыми полосами и горящими
// кометами; ночь — точки, созвездие у курсора и падающие звёзды.
// Фон виден только в просветах между карточками, поэтому он приглушён и не спорит с ними.
const RATIO_CAP = 1.5;
const FADE_S = 1.4;
const STEP = 12;
const TAIL = 28;
const TAU = Math.PI * 2;
const LEVELS = { off: 0, quiet: 0.55, normal: 1, bright: 1.6 };
const PARTS = ["morning", "day", "evening", "night"];

export function initAmbient() {
  const boot = motionBoot();
  if (!boot || !document.querySelector(".shell")) {
    return;
  }
  const canvas = document.createElement("canvas");
  canvas.className = "ambient";
  canvas.setAttribute("aria-hidden", "true");
  document.body.prepend(canvas);
  const ctx = canvas.getContext("2d");
  const root = document.documentElement;
  const fine = window.matchMedia("(hover: hover) and (pointer: fine)");
  const s = {
    ratio: 1,
    width: 0,
    height: 0,
    wide: false,
    part: "",
    previous: "",
    auto: "",
    mix: 1,
    level: 1,
    comets: true,
    colors: readColors(root),
    target: { x: -1e5, y: -1e5 },
    pointer: { x: -1e5, y: -1e5 },
    running: false,
    last: 0,
    time: 0,
    dt: 0,
    dust: [],
    scenes: {},
  };
  let xs = new Float32Array(0);
  let ys = new Float32Array(0);
  let ys2 = new Float32Array(0);
  const tx = new Float32Array(TAIL + 1);
  const ty = new Float32Array(TAIL + 1);
  const gradients = new Map();
  const cachedGradient = (key, build) => {
    if (!gradients.has(key)) {
      gradients.set(key, build());
    }
    return gradients.get(key);
  };

  // ---------- общие кисти ----------

  // Шлейф: точка 0 — голова. Несколько проходов разной длины и толщины дают сужение
  // к хвосту без стыков; градиент вдоль хорды гасит хвост в прозрачность.
  const stroke = (count, color, alpha, width) => {
    const last = Math.max(1, count - 1);
    if (alpha <= 0.002 || (tx[last] === tx[0] && ty[last] === ty[0])) {
      return;
    }
    const gradient = ctx.createLinearGradient(tx[last], ty[last], tx[0], ty[0]);
    gradient.addColorStop(0, rgba(color, 0));
    gradient.addColorStop(1, rgba(color, alpha));
    ctx.strokeStyle = gradient;
    ctx.lineWidth = width;
    ctx.beginPath();
    ctx.moveTo(tx[last], ty[last]);
    for (let index = last - 1; index >= 0; index -= 1) {
      ctx.lineTo(tx[index], ty[index]);
    }
    ctx.stroke();
  };

  const comet = (color, glow, core, alpha, width, rate = 1) => {
    const r = s.ratio;
    const a = Math.min(1, alpha);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    stroke(Math.round(TAIL * 0.75), glow, a * 0.26, width * 4.6 * r);
    stroke(TAIL + 1, color, a * 0.55, width * 0.4 * r);
    stroke(Math.round(TAIL * 0.6), color, a * 0.85, width * 0.7 * r);
    stroke(Math.round(TAIL * 0.26), color, a, width * r);
    shed(glow, a, rate);
    const radius = (6 + width * 3.2) * r;
    const lifted = root.dataset.theme === "dark";
    if (lifted) {
      ctx.globalCompositeOperation = "lighter";
    }
    const halo = ctx.createRadialGradient(tx[0], ty[0], 0, tx[0], ty[0], radius);
    halo.addColorStop(0, rgba(glow, a * (lifted ? 0.28 : 0.55)));
    halo.addColorStop(1, rgba(glow, 0));
    ctx.fillStyle = halo;
    ctx.beginPath();
    ctx.arc(tx[0], ty[0], radius, 0, TAU);
    ctx.fill();
    ctx.globalCompositeOperation = "source-over";
    ctx.fillStyle = rgba(core, a);
    ctx.beginPath();
    ctx.arc(tx[0], ty[0], (0.9 + width * 0.45) * r, 0, TAU);
    ctx.fill();
  };

  // Искры, которые голова кометы роняет за собой: живут около секунды и медленно оседают.
  const shed = (color, alpha, rate) => {
    if (!s.dt || s.dust.length > 240 || Math.random() > s.dt * 26 * rate) {
      return;
    }
    const r = s.ratio;
    const back = Math.sign(tx[1] - tx[0]) || 0;
    s.dust.push({
      x: tx[0],
      y: ty[0],
      vx: (back * (6 + Math.random() * 18) + (Math.random() - 0.5) * 12) * r,
      vy: ((Math.random() - 0.5) * 16 + 5) * r,
      life: 0,
      total: 0.8 + Math.random() * 1,
      size: (0.5 + Math.random() * 1.2) * r,
      color,
      alpha,
    });
  };

  const drawDust = (dt) => {
    if (!s.dust.length) {
      return;
    }
    s.dust = s.dust.filter((item) => item.life < item.total);
    s.dust.forEach((item) => {
      item.life += dt;
      item.x += item.vx * dt;
      item.y += item.vy * dt;
      const fade = Math.max(0, 1 - item.life / item.total) ** 1.4;
      ctx.fillStyle = rgba(item.color, Math.min(1, item.alpha * fade * 0.9));
      ctx.beginPath();
      ctx.arc(item.x, item.y, item.size, 0, TAU);
      ctx.fill();
    });
  };

  // Высота линии в точке x. Курсор раздвигает линии мягко, по колоколу, ближние — сильнее.
  const lineY = (line, x, t) => {
    const r = s.ratio;
    const u = x / r;
    let y =
      s.height * line.base +
      (Math.sin(u * line.k1 + t * line.s1 + line.phase) * line.amp +
        Math.sin(u * line.k2 - t * line.s2 + line.phase * 2) * line.amp * 0.32 +
        Math.sin(u * line.k3 + t * line.s3 + line.phase * 3) * line.amp * 0.09) *
        r;
    const dx = x - s.pointer.x;
    const dy = y - s.pointer.y;
    const reach = 150 * r;
    const near = dx * dx + dy * dy;
    if (near < reach * reach * 6) {
      const distance = Math.sqrt(near) || 1;
      const push = Math.exp(-near / (2 * reach * reach)) * reach * (0.22 + 0.36 * line.depth);
      y += (dy / distance) * push;
    }
    return y;
  };

  const sample = (line, t, into) => {
    for (let index = 0; index < xs.length; index += 1) {
      into[index] = lineY(line, xs[index], t);
    }
  };

  // Гладкая кривая через середины отрезков: без изломов на любом шаге выборки.
  const trace = (values, reverse) => {
    const n = xs.length;
    if (!reverse) {
      ctx.moveTo(xs[0], values[0]);
      for (let index = 1; index < n - 1; index += 1) {
        ctx.quadraticCurveTo(xs[index], values[index], (xs[index] + xs[index + 1]) / 2, (values[index] + values[index + 1]) / 2);
      }
      ctx.lineTo(xs[n - 1], values[n - 1]);
      return;
    }
    ctx.lineTo(xs[n - 1], values[n - 1]);
    for (let index = n - 2; index > 0; index -= 1) {
      ctx.quadraticCurveTo(xs[index], values[index], (xs[index] + xs[index - 1]) / 2, (values[index] + values[index - 1]) / 2);
    }
    ctx.lineTo(xs[0], values[0]);
  };

  const lineComet = (item, t, alpha, color, glow, core, width) => {
    if (item.wait > 0) {
      return;
    }
    const step = (item.tail * s.ratio) / TAIL;
    for (let index = 0; index <= TAIL; index += 1) {
      const x = item.x - item.dir * step * index;
      tx[index] = x;
      ty[index] = lineY(item.line, x, t);
    }
    comet(color, glow, core, alpha * item.bright, width * (0.7 + 0.5 * item.line.depth));
  };

  const moveLineComets = (scene, dt, speedScale) => {
    const r = s.ratio;
    scene.comets.forEach((item) => {
      if (item.wait > 0) {
        item.wait -= dt;
        return;
      }
      item.x += item.dir * item.speed * speedScale * r * dt;
      const margin = item.tail * r + 40 * r;
      if ((item.dir > 0 && item.x > s.width + margin) || (item.dir < 0 && item.x < -margin)) {
        launch(scene, item, false);
      }
    });
  };

  const launch = (scene, item, midway) => {
    const r = s.ratio;
    item.line = scene.lines[Math.floor(Math.random() * scene.lines.length)];
    item.dir = Math.random() < scene.forward ? 1 : -1;
    item.speed = scene.speed[0] + Math.random() * (scene.speed[1] - scene.speed[0]);
    item.speed *= 0.55 + 0.6 * item.line.depth;
    item.tail = scene.tail[0] + Math.random() * (scene.tail[1] - scene.tail[0]);
    item.bright = 0.75 + Math.random() * 0.35;
    item.hue = Math.random();
    const margin = item.tail * r + 20 * r;
    item.x = midway ? Math.random() * s.width : item.dir > 0 ? -margin : s.width + margin;
    // Часть комет сразу в пути: неподвижный кадр спокойного режима тоже их показывает.
    item.wait = midway ? (Math.random() < 0.6 ? 0 : Math.random() * 2) : 0.6 + Math.random() * scene.pause;
  };

  const cometCount = (base) => {
    const narrow = s.width / s.ratio < 700 ? 0.6 : 1;
    const level = s.level < 0.8 ? 0.6 : s.level > 1.2 ? 1.4 : 1;
    return Math.max(1, Math.round(base * narrow * level));
  };

  const fillComets = (scene, base) => {
    const want = cometCount(base);
    while (scene.comets.length < want) {
      const item = {};
      launch(scene, item, true);
      scene.comets.push(item);
    }
    scene.comets.length = want;
  };

  // ---------- сцены ----------

  const makeLines = (count, spec) =>
    Array.from({ length: count }, (_, index) => {
      // Глубина вперемешку: дальние тонкие и медленные, ближние плотнее и быстрее.
      const depth = ((index * 7) % count) / Math.max(1, count - 1);
      const length = spec.length * (0.8 + Math.random() * 0.5);
      return {
        base: spec.top + ((index + 0.5) / count) * spec.spread + (Math.random() - 0.5) * 0.02,
        amp: spec.amp * (0.55 + 0.45 * depth) * (0.85 + Math.random() * 0.3),
        k1: 1 / length,
        k2: 1 / (length * (0.32 + Math.random() * 0.1)),
        k3: 1 / (length * 0.12),
        s1: spec.speed * (0.55 + 0.45 * depth),
        s2: spec.speed * 1.4 * (0.6 + 0.4 * depth),
        s3: spec.speed * 2.3,
        phase: Math.random() * TAU,
        depth,
        accent: spec.accent.includes(index),
      };
    });

  const scenes = {
    morning: {
      make() {
        return {
          rays: Array.from({ length: 10 }, (_, index) => ({
            angle: 0.14 + index * 0.135 + (Math.random() - 0.5) * 0.03,
            spread: 0.007 + Math.random() * 0.011,
            phase: Math.random() * TAU,
            glow: 0,
            tone: index % 5 === 2 ? "hot" : index % 2 ? "lime" : "white",
          })),
          motes: Array.from({ length: 64 }, () => ({
            x: Math.random(),
            y: Math.random(),
            vx: 0.004 + Math.random() * 0.008,
            vy: -0.003 - Math.random() * 0.007,
            size: 0.6 + Math.random() * 1.4,
            phase: Math.random() * TAU,
            warm: Math.random() < 0.45,
          })),
          flashes: [],
        };
      },
      update(scene, dt, t) {
        scene.motes.forEach((mote) => {
          mote.x += mote.vx * dt * (1 + 0.3 * Math.sin(t * 0.4 + mote.phase));
          mote.y += mote.vy * dt;
          if (mote.x > 1.05) {
            mote.x = -0.05;
          }
          if (mote.y < -0.05) {
            mote.y = 1.05;
          }
        });
        const want = s.comets ? cometCount(3) : 0;
        scene.flashes = scene.flashes.filter((flash) => flash.d < flash.end).slice(0, want);
        while (scene.flashes.length < want) {
          scene.flashes.push(flashOn(scene, true));
        }
        scene.flashes.forEach((flash) => {
          if (flash.wait > 0) {
            flash.wait -= dt;
          } else {
            flash.d += flash.speed * s.ratio * dt;
          }
        });
      },
      draw(scene, t, alpha) {
        const { ratio: r, width, height, colors } = s;
        const ox = -width * 0.04;
        const oy = -height * 0.14;
        const reach = Math.hypot(width, height) * 1.35;
        const towards = Math.atan2(s.pointer.y - oy, s.pointer.x - ox);
        // Тёплое небо в углу, откуда идут лучи.
        const dawn = cachedGradient("dawn", () => {
          const value = ctx.createRadialGradient(ox, oy, 0, ox, oy, reach * 0.55);
          value.addColorStop(0, rgba(colors.warm, 0.16));
          value.addColorStop(1, rgba(colors.warm, 0));
          return value;
        });
        ctx.save();
        ctx.globalAlpha = alpha;
        ctx.fillStyle = dawn;
        ctx.fillRect(0, 0, width, height);
        ctx.restore();
        scene.rays.forEach((ray, index) => {
          const angle = ray.angle + Math.sin(t * 0.17 + ray.phase) * 0.02;
          const near = Math.abs(towards - angle) < ray.spread + 0.04 ? 1 : 0;
          ray.glow += (near - ray.glow) * 0.07;
          const spread = ray.spread * (0.8 + 0.35 * Math.sin(t * 0.33 + index)) + ray.glow * 0.008;
          const base = ray.tone === "white" ? 0.58 : ray.tone === "lime" ? 0.26 : 0.07;
          const color = ray.tone === "white" ? colors.white : ray.tone === "lime" ? colors.lime : colors.hot;
          const strength = Math.min(1, (base + ray.glow * 0.35) * alpha);
          const beam = cachedGradient(`beam-${ray.tone}`, () => {
            const value = ctx.createRadialGradient(ox, oy, 0, ox, oy, reach);
            value.addColorStop(0, rgba(color, 1));
            value.addColorStop(0.4, rgba(color, 0.55));
            value.addColorStop(0.85, rgba(color, 0.12));
            value.addColorStop(1, rgba(color, 0));
            return value;
          });
          ctx.save();
          ctx.globalAlpha = strength;
          ctx.fillStyle = beam;
          ctx.beginPath();
          ctx.moveTo(ox, oy);
          ctx.lineTo(ox + Math.cos(angle - spread) * reach, oy + Math.sin(angle - spread) * reach);
          ctx.lineTo(ox + Math.cos(angle + spread) * reach, oy + Math.sin(angle + spread) * reach);
          ctx.closePath();
          ctx.fill();
          ctx.restore();
        });
        // Пылинки вспыхивают, когда попадают в луч.
        scene.motes.forEach((mote) => {
          const x = mote.x * width;
          const y = mote.y * height;
          const angle = Math.atan2(y - oy, x - ox);
          const lit = scene.rays.some((ray) => Math.abs(angle - ray.angle) < ray.spread * 1.4);
          const twinkle = 0.55 + 0.45 * Math.sin(t * 1.6 + mote.phase);
          const a = (lit ? 0.5 : 0.16) * twinkle * alpha;
          ctx.fillStyle = rgba(mote.warm ? colors.hot : colors.limeDeep, Math.min(1, a));
          ctx.beginPath();
          ctx.arc(x, y, mote.size * r * (lit ? 1.25 : 1), 0, TAU);
          ctx.fill();
        });
        // Вспышки света бегут по лучам от солнца.
        scene.flashes.forEach((flash) => {
          if (flash.wait > 0) {
            return;
          }
          const step = (flash.tail * r) / TAIL;
          for (let index = 0; index <= TAIL; index += 1) {
            const d = Math.max(0, flash.d - step * index);
            tx[index] = ox + Math.cos(flash.ray.angle) * d;
            ty[index] = oy + Math.sin(flash.ray.angle) * d;
          }
          const color = flash.warm ? colors.hot : colors.limeDeep;
          comet(color, flash.warm ? colors.warm : colors.lime, color, 0.6 * alpha, 1.8, 0.7);
        });
      },
    },
    day: {
      make() {
        const scene = {
          lines: makeLines(11, { top: 0.02, spread: 0.98, amp: 22, length: 140, speed: 0.42, accent: [3, 8] }),
          comets: [],
          forward: 0.7,
          speed: [80, 170],
          tail: [200, 360],
          pause: 3.5,
        };
        return scene;
      },
      update(scene, dt) {
        if (s.comets) {
          fillComets(scene, 5);
          moveLineComets(scene, dt, 1);
        }
      },
      draw(scene, t, alpha) {
        const { colors } = s;
        ctx.lineCap = "round";
        scene.lines.forEach((line) => {
          sample(line, t, ys);
          ctx.beginPath();
          trace(ys, false);
          const a = line.accent ? 0.2 : 0.035 + 0.055 * line.depth;
          ctx.strokeStyle = rgba(line.accent ? colors.hot : colors.ink, Math.min(1, a * alpha));
          ctx.lineWidth = (line.accent ? 1.5 : 0.7 + 0.6 * line.depth) * s.ratio;
          ctx.stroke();
        });
        if (s.comets) {
          scene.comets.forEach((item) => {
            const ink = item.hue > 0.74;
            const color = ink ? colors.ink : colors.hot;
            lineComet(item, t, (ink ? 0.42 : 0.75) * alpha, color, ink ? colors.ink : colors.warm, color, 1.7);
          });
        }
      },
    },
    evening: {
      make() {
        return {
          lines: makeLines(7, { top: 0.04, spread: 0.96, amp: 36, length: 150, speed: 0.34, accent: [] }),
          comets: [],
          forward: 0.55,
          speed: [70, 140],
          tail: [300, 520],
          pause: 3,
        };
      },
      update(scene, dt) {
        if (s.comets) {
          fillComets(scene, 4);
          moveLineComets(scene, dt, 1);
        }
      },
      draw(scene, t, alpha) {
        const { width, height, colors } = s;
        const sun = cachedGradient("sun", () => {
          const value = ctx.createRadialGradient(width * 0.86, height * 1.02, 0, width * 0.86, height * 1.02, Math.max(width, height) * 0.75);
          value.addColorStop(0, rgba(colors.hot, 0.1));
          value.addColorStop(0.5, rgba(colors.warm, 0.05));
          value.addColorStop(1, rgba(colors.warm, 0));
          return value;
        });
        ctx.save();
        ctx.globalAlpha = alpha;
        ctx.fillStyle = sun;
        ctx.fillRect(0, 0, width, height);
        ctx.restore();
        // Шёлк: мягкая заливка между соседними волнами через одну.
        for (let index = 0; index + 1 < scene.lines.length; index += 2) {
          sample(scene.lines[index], t * 0.8, ys);
          sample(scene.lines[index + 1], t * 0.8, ys2);
          ctx.beginPath();
          trace(ys, false);
          trace(ys2, true);
          ctx.closePath();
          ctx.fillStyle = rgba(colors.warm, Math.min(1, 0.06 * alpha));
          ctx.fill();
        }
        ctx.lineCap = "round";
        scene.lines.forEach((line, index) => {
          sample(line, t * 0.8, ys);
          const odd = index % 2 === 1;
          ctx.beginPath();
          trace(ys, false);
          ctx.strokeStyle = rgba(odd ? colors.hot : colors.warm, Math.min(1, (odd ? 0.15 : 0.3) * (0.7 + 0.5 * line.depth) * alpha));
          ctx.lineWidth = (odd ? 1.6 : 2.6) * (0.75 + 0.4 * line.depth) * s.ratio;
          ctx.stroke();
        });
        if (s.comets) {
          scene.comets.forEach((item) => {
            lineComet(item, t * 0.8, 0.9 * alpha, colors.hot, colors.warm, colors.glow, 2.8);
          });
        }
      },
    },
    night: {
      make() {
        const count = s.width / s.ratio < 700 ? 56 : 96;
        return {
          stars: Array.from({ length: count }, () => {
            const depth = Math.random();
            return {
              x: Math.random(),
              y: Math.random(),
              depth,
              size: 0.6 + depth * 1.5,
              speed: 0.000012 + depth * 0.00005,
              phase: Math.random() * TAU,
              blink: 0.6 + Math.random() * 1.4,
              bright: Math.random() < 0.07,
            };
          }),
          meteors: [],
          next: 1.5 + Math.random() * 3,
        };
      },
      update(scene, dt) {
        scene.stars.forEach((star) => {
          star.x = (star.x + star.speed * dt * 60) % 1;
        });
        scene.meteors = scene.meteors.filter((item) => item.life > 0);
        scene.meteors.forEach((item) => {
          item.x += item.vx * s.ratio * dt;
          item.y += item.vy * s.ratio * dt;
          item.life -= dt;
        });
        if (!s.comets) {
          return;
        }
        scene.next -= dt;
        if (scene.next <= 0) {
          scene.meteors.push(meteor());
          const gap = s.level > 1.2 ? 2.2 : s.level < 0.8 ? 7 : 4;
          scene.next = gap + Math.random() * gap;
        }
      },
      draw(scene, t, alpha) {
        const { ratio: r, width, height, colors } = s;
        const reach = 170 * r;
        const near = [];
        scene.stars.forEach((star) => {
          const x = star.x * width;
          const y = star.y * height;
          const glow = (0.14 + 0.24 * star.depth) * (0.6 + 0.4 * Math.sin(t * star.blink + star.phase));
          if (star.bright) {
            const lifted = root.dataset.theme === "dark";
            if (lifted) {
              ctx.globalCompositeOperation = "lighter";
            }
            const halo = ctx.createRadialGradient(x, y, 0, x, y, 7 * r);
            halo.addColorStop(0, rgba(colors.hot, (lifted ? 0.12 : 0.22) * alpha));
            halo.addColorStop(1, rgba(colors.hot, 0));
            ctx.fillStyle = halo;
            ctx.beginPath();
            ctx.arc(x, y, 7 * r, 0, TAU);
            ctx.fill();
            ctx.globalCompositeOperation = "source-over";
          }
          ctx.fillStyle = rgba(colors.ink, Math.min(1, glow * alpha));
          ctx.beginPath();
          ctx.arc(x, y, star.size * r, 0, TAU);
          ctx.fill();
          const distance = Math.hypot(x - s.pointer.x, y - s.pointer.y);
          if (distance < reach) {
            near.push({ x, y, k: 1 - distance / reach });
          }
        });
        // Созвездие: курсор тянет к себе ближние точки, точки рядом связываются между собой.
        ctx.lineWidth = r;
        near.forEach((star, index) => {
          ctx.strokeStyle = rgba(colors.hot, Math.min(1, 0.42 * star.k * alpha));
          ctx.beginPath();
          ctx.moveTo(star.x, star.y);
          ctx.lineTo(s.pointer.x, s.pointer.y);
          ctx.stroke();
          for (let other = index + 1; other < near.length; other += 1) {
            const gap = Math.hypot(star.x - near[other].x, star.y - near[other].y);
            if (gap < 110 * r) {
              ctx.strokeStyle = rgba(colors.ink, Math.min(1, 0.2 * star.k * near[other].k * alpha));
              ctx.beginPath();
              ctx.moveTo(star.x, star.y);
              ctx.lineTo(near[other].x, near[other].y);
              ctx.stroke();
            }
          }
        });
        scene.meteors.forEach((item) => {
          const fade = Math.min(1, item.life / 0.35, (item.total - item.life) / 0.2);
          const length = Math.hypot(item.vx, item.vy);
          const step = (item.tail * r) / TAIL;
          for (let index = 0; index <= TAIL; index += 1) {
            tx[index] = item.x - (item.vx / length) * step * index;
            ty[index] = item.y - (item.vy / length) * step * index;
          }
          comet(colors.ink, colors.hot, colors.hot, 0.55 * fade * alpha, 1.6, 1.6);
        });
      },
    },
  };

  const flashOn = (scene, fresh) => ({
    ray: scene.rays[Math.floor(Math.random() * scene.rays.length)],
    d: 0,
    end: Math.hypot(s.width, s.height) * 1.2,
    speed: 260 + Math.random() * 220,
    tail: 120 + Math.random() * 120,
    warm: Math.random() < 0.5,
    wait: fresh ? Math.random() * 4 : 0,
  });

  const meteor = () => {
    const left = Math.random() < 0.5;
    const speed = 620 + Math.random() * 380;
    const angle = (left ? Math.PI - 0.42 : 0.42) + (Math.random() - 0.5) * 0.3;
    const life = 1.1 + Math.random() * 0.6;
    return {
      x: (left ? 0.35 + Math.random() * 0.75 : -0.1 + Math.random() * 0.75) * s.width,
      y: (-0.05 + Math.random() * 0.4) * s.height,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      tail: 170 + Math.random() * 120,
      life,
      total: life,
    };
  };

  const sceneOf = (part) => {
    if (!s.scenes[part]) {
      s.scenes[part] = scenes[part].make();
    }
    return s.scenes[part];
  };

  // ---------- кадр ----------

  const resize = () => {
    s.ratio = Math.min(window.devicePixelRatio || 1, RATIO_CAP);
    s.width = Math.round(window.innerWidth * s.ratio);
    s.height = Math.round(window.innerHeight * s.ratio);
    s.wide = window.innerWidth >= 1100;
    canvas.width = s.width;
    canvas.height = s.height;
    gradients.clear();
    const count = Math.ceil(s.width / (STEP * s.ratio)) + 3;
    xs = new Float32Array(count);
    ys = new Float32Array(count);
    ys2 = new Float32Array(count);
    for (let index = 0; index < count; index += 1) {
      xs[index] = (index - 1) * STEP * s.ratio;
    }
    s.scenes = {};
    paintStill();
  };

  const autoPart = () => {
    const hour = zonedHour(boot, serverNow(boot));
    const split = Number(boot.split) || 5;
    if (hour < split) {
      return "night";
    }
    if (hour < 12) {
      return "morning";
    }
    return hour < 18 ? "day" : "evening";
  };

  const choose = () => {
    const auto = autoPart();
    if (auto !== s.auto) {
      s.auto = auto;
      root.dataset.autopart = auto;
      document.dispatchEvent(new CustomEvent("nashden:daypart", { detail: { part: auto } }));
    }
    const picked = getPref("scene");
    const part = PARTS.includes(picked) ? picked : auto;
    if (part === s.part) {
      return;
    }
    s.previous = s.part;
    s.part = part;
    s.mix = s.previous && !isCalm() && s.level > 0 ? 0 : 1;
    root.dataset.daypart = part;
    paintStill();
  };

  const paint = (dt) => {
    s.pointer.x += (s.target.x - s.pointer.x) * 0.14;
    s.pointer.y += (s.target.y - s.pointer.y) * 0.14;
    ctx.globalCompositeOperation = "source-over";
    ctx.clearRect(0, 0, s.width, s.height);
    if (s.level <= 0 || !s.part) {
      return;
    }
    if (s.previous && s.mix < 1) {
      s.mix = Math.min(1, s.mix + dt / FADE_S);
    }
    const eased = s.mix * s.mix * (3 - 2 * s.mix);
    const list = [];
    if (s.previous && eased < 1) {
      list.push([s.previous, 1 - eased]);
    }
    list.push([s.part, eased]);
    s.dt = dt;
    list.forEach(([part, weight]) => {
      const scene = sceneOf(part);
      scenes[part].update(scene, dt, s.time);
      scenes[part].draw(scene, s.time, weight * s.level);
    });
    drawDust(dt);
    if (s.wide) {
      // Края широкого экрана растворяют линии, чтобы они не обрывались о рамку окна.
      const edge = s.width * 0.06;
      ctx.globalCompositeOperation = "destination-out";
      const left = cachedGradient("edge-left", () => {
        const value = ctx.createLinearGradient(0, 0, edge, 0);
        value.addColorStop(0, "rgba(0, 0, 0, 1)");
        value.addColorStop(1, "rgba(0, 0, 0, 0)");
        return value;
      });
      ctx.fillStyle = left;
      ctx.fillRect(0, 0, edge, s.height);
      const right = cachedGradient("edge-right", () => {
        const value = ctx.createLinearGradient(s.width - edge, 0, s.width, 0);
        value.addColorStop(0, "rgba(0, 0, 0, 0)");
        value.addColorStop(1, "rgba(0, 0, 0, 1)");
        return value;
      });
      ctx.fillStyle = right;
      ctx.fillRect(s.width - edge, 0, edge, s.height);
      ctx.globalCompositeOperation = "source-over";
    }
  };

  // Спокойный режим и остановка: один неподвижный кадр.
  const paintStill = () => {
    if (!s.running) {
      paint(0);
    }
  };

  const frame = (now) => {
    if (!s.running) {
      return;
    }
    window.requestAnimationFrame(frame);
    // Широкий экран с мышью — 60 кадров, телефон — 30: фон медленный, батарея важнее.
    const budget = fine.matches && window.innerWidth >= 960 ? 0 : 32;
    if (now - s.last < budget) {
      return;
    }
    // После скрытой вкладки шаг не прыгает: время фона просто продолжается.
    const dt = s.last ? Math.min((now - s.last) / 1000, 0.05) : 0.016;
    s.last = now;
    s.time += dt;
    paint(dt);
  };

  const run = () => {
    const should = !isCalm() && !document.hidden && s.level > 0;
    if (should && !s.running) {
      s.running = true;
      s.last = 0;
      window.requestAnimationFrame(frame);
    } else if (!should) {
      s.running = false;
      paint(0);
    }
  };

  const applyPrefs = () => {
    s.level = LEVELS[getPref("bg")] ?? 1;
    s.comets = getPref("comets") !== "off";
    Object.values(s.scenes).forEach((scene) => {
      if (scene.comets) {
        scene.comets.length = 0;
      }
    });
  };

  window.addEventListener(
    "pointermove",
    (event) => {
      if (event.pointerType === "touch") {
        return;
      }
      s.target.x = event.clientX * s.ratio;
      s.target.y = event.clientY * s.ratio;
      if (s.pointer.x < -1e4) {
        s.pointer.x = s.target.x;
        s.pointer.y = s.target.y;
      }
    },
    { passive: true },
  );
  document.addEventListener("mouseleave", () => {
    s.target.x = -1e5;
    s.target.y = -1e5;
  });
  window.addEventListener("resize", resize, { passive: true });
  document.addEventListener("visibilitychange", run);
  document.addEventListener("nashden:theme", () => {
    s.colors = readColors(root);
    gradients.clear();
    run();
    paintStill();
  });
  onCalmChange(() => {
    s.mix = 1;
    run();
  });
  onPrefs((name) => {
    if (name === "palette" || name === "theme") {
      s.colors = readColors(root);
      gradients.clear();
    }
    if (name === "bg" || name === "comets") {
      applyPrefs();
    }
    if (name === "scene") {
      choose();
    }
    run();
    paintStill();
  });
  applyPrefs();
  // Неподвижный кадр показывает фон в середине движения, а не пустой первый миг.
  s.time = 40 + Math.random() * 40;
  resize();
  choose();
  window.setInterval(choose, 60 * 1000);
  run();
}

function readColors(root) {
  const style = getComputedStyle(root);
  const pick = (name, fallback) => toRgb(style.getPropertyValue(name).trim()) || fallback;
  const hot = pick("--hot", [255, 74, 28]);
  const white = [255, 255, 255];
  return {
    ink: pick("--fg", [11, 11, 12]),
    hot,
    lime: pick("--lime", [207, 255, 61]),
    limeDeep: pick("--lime-deep", [159, 212, 0]),
    warm: mix(hot, white, 0.42),
    glow: mix(hot, white, 0.7),
    white,
  };
}

function toRgb(text) {
  const match = /^#([0-9a-f]{6})$/i.exec(text);
  if (!match) {
    return null;
  }
  const value = Number.parseInt(match[1], 16);
  return [value >> 16, (value >> 8) & 255, value & 255];
}

function mix(from, to, share) {
  return from.map((value, index) => Math.round(value + (to[index] - value) * share));
}

function rgba(color, alpha) {
  return `rgba(${color[0]}, ${color[1]}, ${color[2]}, ${Math.max(0, alpha).toFixed(3)})`;
}
