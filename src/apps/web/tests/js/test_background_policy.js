import { backgroundPolicy } from "../modules/background-policy.js";

// Запускается как внешний модуль в изолированной странице проверки, без библиотек.
const cases = [
  ["normal", false, {}, "normal", false],
  ["normal", false, { saveData: true }, "quiet", true],
  ["normal", false, { cores: 4 }, "quiet", true],
  ["normal", false, { memory: 2 }, "quiet", true],
  ["normal", false, { cores: 5, memory: 3 }, "normal", false],
  ...["off", "quiet", "normal", "bright"].map((value) => [value, true, { saveData: true, cores: 2, memory: 1 }, value, false]),
];
for (const [value, explicit, device, expected, economical] of cases) {
  const result = backgroundPolicy(value, explicit, device);
  if (result.value !== expected || result.economical !== economical) {
    throw new Error(JSON.stringify({ value, explicit, device, result, expected, economical }));
  }
}
document.getElementById("test-results").textContent = `${cases.length} проверок бережного режима прошли`;
