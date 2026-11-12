// Время — только Europe/Minsk (UTC+3 без перехода на летнее время с 2011 г.).
// «Сейчас» берётся из /api/demo/clock, не из браузера. Сравниваем моменты, а не строки:
// точка ряда 2026-11-21T21:00:00Z — это сутки 22 ноября.

export const MINSK_OFFSET_MIN = 180;
const MS_DAY = 86_400_000;

const MONTHS = ['янв', 'февр', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сент', 'окт', 'нояб', 'дек'];
const WEEKDAYS = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];

export function ms(iso: string): number {
  return Date.parse(iso);
}

/** Поля даты по Минску. Принимает момент ISO или ключ суток YYYY-MM-DD. */
function minsk(isoOrDay: string): Date {
  if (/^\d{4}-\d{2}-\d{2}$/.test(isoOrDay)) return new Date(`${isoOrDay}T00:00:00Z`);
  return new Date(ms(isoOrDay) + MINSK_OFFSET_MIN * 60_000);
}

const pad = (n: number) => String(n).padStart(2, '0');

/** Сутки по Минску: YYYY-MM-DD. */
export function dayKey(isoOrDay: string): string {
  const d = minsk(isoOrDay);
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
}

export function addDaysToKey(key: string, days: number): string {
  const d = new Date(`${key}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
}

/** Начало суток по Минску как ISO с поясом (для параметров from/to). */
export function dayStartIso(key: string): string {
  return `${key}T00:00:00+03:00`;
}

/** «22 нояб» */
export function fmtDay(isoOrDay: string): string {
  const d = minsk(isoOrDay);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
}

/** «пн, 23 нояб» */
export function fmtDayWeek(isoOrDay: string): string {
  const d = minsk(isoOrDay);
  return `${WEEKDAYS[d.getUTCDay()]}, ${fmtDay(isoOrDay)}`;
}

/** «09:00» */
export function fmtTime(iso: string): string {
  const d = minsk(iso);
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

/** «пн, 23 нояб, 09:00» */
export function fmtClock(iso: string): string {
  return `${fmtDayWeek(iso)}, ${fmtTime(iso)}`;
}

/** «23 нояб, 09:00» */
export function fmtDateTime(iso: string): string {
  return `${fmtDay(iso)}, ${fmtTime(iso)}`;
}

/** Разница в сутках (дробная): b − a. */
export function daysBetween(aIso: string, bIso: string): number {
  return (ms(bIso) - ms(aIso)) / MS_DAY;
}

/** Целые календарные сутки между ключами: to − from. */
export function dayDiff(fromKey: string, toKey: string): number {
  return Math.round((Date.parse(`${toKey}T00:00:00Z`) - Date.parse(`${fromKey}T00:00:00Z`)) / MS_DAY);
}

/** Свежесть относительно демо-часов: «сегодня», «вчера», «3 дн. назад», «через 2 дн.». */
export function relativeDay(isoOrDay: string, nowIso: string): string {
  const diff = dayDiff(dayKey(isoOrDay), dayKey(nowIso));
  if (diff === 0) return 'сегодня';
  if (diff === 1) return 'вчера';
  if (diff === -1) return 'завтра';
  if (diff > 1) return `${diff} дн. назад`;
  return `через ${-diff} дн.`;
}

/** ISO момента + N суток (для «срок через 3 дня» от демо-часов). */
export function addDaysIso(iso: string, days: number): string {
  const d = minsk(iso);
  d.setUTCDate(d.getUTCDate() + days);
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}T${pad(d.getUTCHours())}:${pad(
    d.getUTCMinutes(),
  )}:00+03:00`;
}
