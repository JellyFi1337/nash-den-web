import { initAmbient } from "./modules/ambient.js";
import { initCelebrate } from "./modules/celebrate.js";
import { initClocks } from "./modules/clock.js";
import { initCopyText } from "./modules/copytext.js";
import { initGate } from "./modules/gate.js";
import { initHeatTips } from "./modules/heat.js";
import { initHscroll } from "./modules/hscroll.js";
import { initDayToc } from "./modules/daytoc.js";
import { initOdometer } from "./modules/odometer.js";
import { initPulse } from "./modules/pulse.js";
import { initReveal } from "./modules/reveal.js";
import { initSettings } from "./modules/settings.js";
import { initSearch } from "./modules/search.js";
import { initSpotlight } from "./modules/spotlight.js";
import { initSwipe } from "./modules/swipe.js";
import { initSharecard } from "./modules/sharecard.js";
import { initToast } from "./modules/toast.js";

// Порядок важен: появление снимает «ожидание» с чисел первым, до любых перерисовок.
initReveal();
initHscroll();
initDayToc();
initSettings();
initSearch();
initToast();
initGate();
initClocks();
initAmbient();
initSpotlight();
initHeatTips();
if (document.querySelector("[data-odo]")) {
  initOdometer();
}
if (document.querySelector("[data-celebrate]")) {
  initCelebrate();
}
if (document.querySelector("[data-pulse]")) {
  initPulse();
}
if (document.querySelector("[data-swipe]")) {
  initSwipe();
}
if (document.querySelector("[data-sharecard]")) {
  initSharecard();
}
if (document.querySelector("[data-copy]")) {
  initCopyText();
}
