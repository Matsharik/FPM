// Числа по-русски: десятичная запятая, неразрывный пробел перед единицей.
// Единица всегда приходит из поля `unit` ответа — здесь её только печатаем.

export const NBSP = ' ';
const MINUS = '−';

function digitsFor(abs: number): number {
  if (abs >= 1000) return 0;
  if (abs >= 100) return 1;
  return 2;
}

export function fmtNum(value: number | null | undefined, maxFrac?: number): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const digits = maxFrac ?? digitsFor(Math.abs(value));
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: digits, minimumFractionDigits: 0 })
    .format(value)
    .replace(/[  ]/g, NBSP)
    .replace('-', MINUS);
}

export function fmtValue(value: number | null | undefined, unit?: string | null, maxFrac?: number): string {
  const n = fmtNum(value, maxFrac);
  if (n === '—' || !unit) return n;
  return `${n}${NBSP}${unit}`;
}

/** Единица изменения: у процентов — процентные пункты. */
export function deltaUnit(unit?: string | null): string {
  if (!unit) return '';
  return unit.startsWith('%') ? 'п.п.' : unit;
}

export function fmtDelta(value: number | null | undefined, unit?: string | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const sign = value > 0 ? '+' : value < 0 ? MINUS : '';
  const body = fmtNum(Math.abs(value));
  const u = deltaUnit(unit);
  return `${sign}${body}${u ? NBSP + u : ''}`;
}

/** Вес связи: «0,6», «0,25». */
export function fmtWeight(value: number | null | undefined): string {
  return fmtNum(value, 2);
}

/** Доля 0..1 → «92 %». */
export function fmtShare(value: number | null | undefined, maxFrac = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${fmtNum(value * 100, maxFrac)}${NBSP}%`;
}

/** Склонение: plural(3, ['день', 'дня', 'дней']). */
export function plural(n: number, forms: [string, string, string]): string {
  const a = Math.abs(n) % 100;
  const b = a % 10;
  if (a > 10 && a < 20) return forms[2];
  if (b > 1 && b < 5) return forms[1];
  if (b === 1) return forms[0];
  return forms[2];
}

export function countLabel(n: number, forms: [string, string, string]): string {
  return `${fmtNum(n, 0)}${NBSP}${plural(n, forms)}`;
}
