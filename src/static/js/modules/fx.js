import { isCalm } from "./motion.js";
import { getPref } from "./prefs.js";

// Искры от аватара при новой отметке и конфетти, когда на связи все.
// Холст поверх страницы создаётся при первом событии и рисует, только пока есть частицы.
// Цвета — из текущей палитры: в «тихой» искры тоже приглушены.
const FALLBACK = ["#CFFF3D", "#FF4A1C", "#0B0B0C"];
let canvas = null;
let context = null;
let particles = [];
let running = false;
let ratio = 1;

export function sparksFrom(el) {
  if (!allowed() || !el) {
    return;
  }
  const rect = el.getBoundingClientRect();
  if (rect.bottom < 0 || rect.top > window.innerHeight) {
    return;
  }
  ensure();
  const colors = palette();
  const x = (rect.left + rect.width / 2) * ratio;
  const y = (rect.top + rect.height / 2) * ratio;
  for (let index = 0; index < 22; index += 1) {
    const angle = Math.random() * Math.PI * 2;
    const speed = (2 + Math.random() * 4.5) * ratio;
    particles.push({
      x,
      y,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed - 1.6 * ratio,
      gravity: 0.2 * ratio,
      life: 1,
      fade: 0.026,
      size: (3 + Math.random() * 3) * ratio,
      color: colors[index % 2],
      turn: 0,
      spin: 0,
      ribbon: false,
    });
  }
  start();
}

export function confetti() {
  if (!allowed()) {
    return;
  }
  ensure();
  const colors = palette();
  const width = canvas.width;
  const height = canvas.height;
  for (let index = 0; index < 150; index += 1) {
    particles.push({
      x: Math.random() * width,
      y: -20 * ratio - Math.random() * height * 0.5,
      vx: (Math.random() - 0.5) * 2.2 * ratio,
      vy: (1.2 + Math.random() * 2.6) * ratio,
      gravity: 0.035 * ratio,
      life: 1.7,
      fade: 0.0065,
      size: (6 + Math.random() * 6) * ratio,
      color: colors[index % 3],
      turn: Math.random() * Math.PI * 2,
      spin: (Math.random() - 0.5) * 0.24,
      ribbon: true,
    });
  }
  start();
}

function allowed() {
  return !isCalm() && getPref("sparks") !== "off";
}

function palette() {
  const style = getComputedStyle(document.documentElement);
  return ["--lime", "--hot", "--fg"].map(
    (name, index) => style.getPropertyValue(name).trim() || FALLBACK[index],
  );
}

function ensure() {
  if (!canvas) {
    canvas = document.createElement("canvas");
    canvas.className = "fx-layer";
    canvas.setAttribute("aria-hidden", "true");
    document.body.appendChild(canvas);
    context = canvas.getContext("2d");
    window.addEventListener("resize", size, { passive: true });
  }
  size();
}

function size() {
  ratio = Math.min(window.devicePixelRatio || 1, 2);
  const width = Math.round(window.innerWidth * ratio);
  const height = Math.round(window.innerHeight * ratio);
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
}

function start() {
  if (running) {
    return;
  }
  running = true;
  window.requestAnimationFrame(frame);
}

function frame() {
  context.clearRect(0, 0, canvas.width, canvas.height);
  particles = particles.filter((item) => item.life > 0 && item.y < canvas.height + 40 * ratio);
  particles.forEach((item) => {
    item.vy += item.gravity;
    item.vx *= 0.995;
    item.x += item.vx;
    item.y += item.vy;
    item.life -= item.fade;
    item.turn += item.spin;
    context.globalAlpha = Math.min(1, item.life);
    context.fillStyle = item.color;
    context.save();
    context.translate(item.x, item.y);
    context.rotate(item.turn);
    if (item.ribbon) {
      // Лента конфетти «переворачивается»: ширина меняется по синусу.
      context.scale(Math.cos(item.turn * 1.7), 1);
      context.fillRect(-item.size / 2, -item.size / 4, item.size, item.size / 2);
    } else {
      context.fillRect(-item.size / 2, -item.size / 2, item.size, item.size);
    }
    context.restore();
  });
  context.globalAlpha = 1;
  if (particles.length && !document.hidden) {
    window.requestAnimationFrame(frame);
    return;
  }
  particles = [];
  context.clearRect(0, 0, canvas.width, canvas.height);
  running = false;
}
