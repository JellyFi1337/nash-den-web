// Время сервера в браузере: опорные моменты из #motion-boot и поправка на часы устройства.
// Часы телефона могут спешить, а граница суток считается по Москве, не по поясу устройства.
let cached;
let formatter;

export function motionBoot() {
  if (cached !== undefined) {
    return cached;
  }
  cached = null;
  const node = document.getElementById("motion-boot");
  if (!node) {
    return cached;
  }
  try {
    const data = JSON.parse(node.textContent || "null");
    if (data && Number(data.now) > 0) {
      data.skew = Number(data.now) - Date.now();
      cached = data;
    }
  } catch (error) {
    cached = null;
  }
  return cached;
}

export function serverNow(boot) {
  return Date.now() + (boot ? boot.skew : 0);
}

export function zonedHour(boot, moment) {
  if (formatter === undefined) {
    try {
      formatter = new Intl.DateTimeFormat("en-GB", {
        timeZone: boot.tz,
        hour: "2-digit",
        hourCycle: "h23",
      });
    } catch (error) {
      formatter = null;
    }
  }
  if (!formatter) {
    return new Date(moment).getHours();
  }
  return Number.parseInt(formatter.format(new Date(moment)), 10) % 24;
}
