import { isCalm } from "./motion.js";

export function tapHaptic() {
  if (!isCalm() && navigator.maxTouchPoints > 0) {
    navigator.vibrate?.(10);
  }
}
