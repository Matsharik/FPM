// Одна таблица переводов статусов на весь проект (раздел 3.4).
import type { DeviationStatus, KpiStatus, StageStatus } from '../api/types';

export type Tone = 'ok' | 'warn' | 'crit' | 'unknown' | 'ink';
export type Glyph = 'check' | 'alert' | 'cross' | 'dash' | 'double-check' | 'up' | 'clock' | 'dot';

export interface StatusMeta {
  label: string;
  tone: Tone;
  glyph: Glyph;
}

export const KPI_STATUS: Record<KpiStatus, StatusMeta> = {
  green: { label: 'Норма', tone: 'ok', glyph: 'check' },
  yellow: { label: 'Внимание', tone: 'warn', glyph: 'alert' },
  red: { label: 'Критично', tone: 'crit', glyph: 'cross' },
  unknown: { label: 'Нет данных', tone: 'unknown', glyph: 'dash' },
};

export const DEVIATION_STATUS: Record<DeviationStatus, StatusMeta> = {
  open: { label: 'Открыто', tone: 'crit', glyph: 'dot' },
  assigned: { label: 'Назначено', tone: 'ink', glyph: 'dot' },
  in_progress: { label: 'В работе', tone: 'ink', glyph: 'clock' },
  done: { label: 'Выполнено, ждёт проверки', tone: 'warn', glyph: 'check' },
  verified: { label: 'Проверено: сработало', tone: 'ok', glyph: 'double-check' },
  failed: { label: 'Проверено: не сработало', tone: 'crit', glyph: 'cross' },
  escalated: { label: 'Эскалировано', tone: 'crit', glyph: 'up' },
  closed: { label: 'Закрыто', tone: 'unknown', glyph: 'dash' },
};

export const STAGE_STATUS: Record<StageStatus, StatusMeta> = {
  pending: { label: 'Не начат', tone: 'unknown', glyph: 'dash' },
  in_progress: { label: 'В работе', tone: 'ink', glyph: 'clock' },
  done: { label: 'Готово', tone: 'ok', glyph: 'check' },
  late: { label: 'С опозданием', tone: 'warn', glyph: 'alert' },
  defect: { label: 'Брак', tone: 'crit', glyph: 'cross' },
};

export function asKpiStatus(s: string | null | undefined): KpiStatus {
  return s === 'green' || s === 'yellow' || s === 'red' ? s : 'unknown';
}

const RANK: Record<KpiStatus, number> = { red: 3, yellow: 2, green: 1, unknown: 0 };

export function statusRank(s: string | null | undefined): number {
  return RANK[asKpiStatus(s)];
}

/** Худший статус среди известных; если все неизвестны — unknown. */
export function worstStatus(list: Array<string | null | undefined>): KpiStatus {
  let best: KpiStatus = 'unknown';
  for (const s of list) {
    const k = asKpiStatus(s);
    if (RANK[k] > RANK[best]) best = k;
  }
  return best;
}

/** Цвет текста дельты по trend_quality: ухудшение — оранжевый (у красного KPI — красный). */
export function trendTone(quality: string | null | undefined, status?: string | null): Tone {
  if (quality === 'worsening') return asKpiStatus(status) === 'red' ? 'crit' : 'warn';
  if (quality === 'improving') return 'ok';
  return 'unknown';
}

export const LEVEL_LABEL: Record<string, string> = {
  warn: 'внимание',
  crit: 'критично',
  target: 'цель',
};

export const PRIORITY_LABEL: Record<string, string> = {
  time: 'Срок',
  quality: 'Качество',
  cost: 'Себестоимость',
};
