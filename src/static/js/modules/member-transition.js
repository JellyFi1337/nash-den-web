import { isCalm } from "./motion.js";

// Этот модуль в head с blocking=render: pagereveal приходит до первого кадра страницы.
const KEY = "nashden-member-transition";
let selected = null;
let picked = null;
let named = [];

function forget() {
  try { sessionStorage.removeItem(KEY); } catch (error) { /* Без хранилища — обычный переход. */ }
}
function clearNames() {
  named.forEach((el) => { el.style.viewTransitionName = ""; });
  named = [];
}
function nameElements(container, packet) {
  clearNames();
  const avatar = container.querySelector(".avatar");
  const name = packet.withName ? container.querySelector("[data-member-name]") : null;
  if (avatar) {
    avatar.style.viewTransitionName = `face-${packet.slug}`;
    named.push(avatar);
  }
  if (name) {
    name.style.viewTransitionName = `name-${packet.slug}`;
    named.push(name);
  }
}
document.addEventListener("click", (event) => {
  const target = event.target instanceof Element ? event.target : null;
  const link = target?.closest("a[data-person-link]");
  if (!link || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || isCalm()) {
    return;
  }
  const url = new URL(link.href, location.href);
  const match = /^\/team\/([a-zA-Z0-9_-]+)\/$/.exec(url.pathname);
  if (url.origin !== location.origin || !match || link.target === "_blank") {
    return;
  }
  selected = link;
  picked = { slug: match[1], path: url.pathname, from: location.pathname, time: Date.now(), withName: Boolean(link.querySelector("[data-member-name]")) };
  try { sessionStorage.setItem(KEY, JSON.stringify(picked)); } catch (error) { picked = null; }
}, { capture: true });

window.addEventListener("pageswap", (event) => {
  if (!event.viewTransition || !selected || !picked || isCalm() || document.hidden) {
    return;
  }
  if (event.activation?.entry?.url && new URL(event.activation.entry.url).pathname !== picked.path) {
    forget();
    return;
  }
  nameElements(selected, picked);
  event.viewTransition.finished.finally(clearNames).catch(() => {});
});
window.addEventListener("pagereveal", (event) => {
  let packet;
  try { packet = JSON.parse(sessionStorage.getItem(KEY) || "null"); } catch (error) { return; }
  forget();
  if (!event.viewTransition || isCalm() || document.hidden || !packet || packet.path !== location.pathname || Date.now() - packet.time > 60000) {
    return;
  }
  const header = document.querySelector("[data-member-header]");
  if (!header || header.dataset.memberHeader !== packet.slug) {
    return;
  }
  nameElements(header, packet);
  event.viewTransition.finished.finally(clearNames).catch(() => {});
});
window.addEventListener("pageshow", () => {
  selected = null;
  picked = null;
});
