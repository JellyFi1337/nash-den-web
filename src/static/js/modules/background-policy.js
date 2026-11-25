// Явный выбор важнее экономии: «обычно» тоже считается выбором.
export function backgroundPolicy(value, explicit, { saveData = false, cores = 8, memory = 8 } = {}) {
  const economical = !explicit && (saveData || cores <= 4 || memory <= 2);
  return { value: economical ? "quiet" : value, economical };
}
