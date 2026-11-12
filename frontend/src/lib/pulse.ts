// Шапка-вердикт Пульса и индикаторы приоритетов — только из ответа /api/overview.
import type { KpiStatus } from '../api/types';
import { plural } from './format';
import { PRIORITY_LABEL, asKpiStatus, statusRank, worstStatus } from './status';

export interface TileLike {
  key: string;
  title: string;
  status: string;
  priority: string;
  order: number;
  kpis: number;
  open_deviations?: number;
  main_kpi?: { severity?: number | null } | null;
}

export interface Verdict {
  sentence: string;
  ok: number;
  known: number;
  outOfZone: number;
}

/** «Команда · ресурс» → «Команда»: в фразе нужен процесс, а не подпись плитки. */
export function shortTitle(title: string): string {
  return title.split(' · ')[0] ?? title;
}

function joinTitles(tiles: TileLike[]): string {
  return tiles.map((t) => shortTitle(t.title)).join(', ');
}

export function pulseVerdict(tiles: TileLike[]): Verdict {
  const sorted = [...tiles].sort((a, b) => a.order - b.order);
  const known = sorted.filter((t) => t.kpis > 0 && asKpiStatus(t.status) !== 'unknown');
  const ok = known.filter((t) => t.status === 'green');
  const red = known.filter((t) => t.status === 'red');
  const yellow = known.filter((t) => t.status === 'yellow');
  const outOfZone = sorted.filter((t) => t.kpis === 0).length;
  const parts: string[] = [];
  if (known.length === 0) {
    parts.push('В вашей зоне нет показателей процессов.');
  } else if (ok.length === known.length) {
    parts.push(
      known.length === 1
        ? 'Процесс в норме.'
        : `Все ${known.length} ${plural(known.length, ['процесс', 'процесса', 'процессов'])} в норме.`,
    );
  } else {
    parts.push(`${ok.length} из ${known.length} ${plural(known.length, ['процесса', 'процессов', 'процессов'])} в норме.`);
  }
  if (red.length) parts.push(`Критично: ${joinTitles(red)}.`);
  if (yellow.length) parts.push(`Внимание: ${joinTitles(yellow)}.`);
  return { sentence: parts.join(' '), ok: ok.length, known: known.length, outOfZone };
}

export interface PriorityIndicator {
  priority: 'time' | 'quality' | 'cost';
  label: string;
  status: KpiStatus;
  tiles: string[];
}

/** «Срок · Качество · Себестоимость»: худший статус плиток с этим priority (только плитки с KPI). */
export function priorityIndicators(tiles: TileLike[]): PriorityIndicator[] {
  const out: PriorityIndicator[] = [];
  for (const priority of ['time', 'quality', 'cost'] as const) {
    const own = tiles.filter((t) => t.priority === priority && t.kpis > 0);
    if (!own.length) continue;
    out.push({
      priority,
      label: PRIORITY_LABEL[priority],
      status: worstStatus(own.map((t) => t.status)),
      tiles: own.sort((a, b) => a.order - b.order).map((t) => t.title),
    });
  }
  return out;
}

/** Самая тяжёлая плитка с открытым отклонением — на ней единственная жёлтая кнопка. */
export function heaviestTileWithDeviation<T extends TileLike>(tiles: T[]): T | null {
  const withDev = tiles.filter((t) => (t.open_deviations ?? 0) > 0);
  if (!withDev.length) return null;
  return withDev.reduce((best, t) => {
    const r = statusRank(t.status) - statusRank(best.status);
    if (r !== 0) return r > 0 ? t : best;
    const s = (t.main_kpi?.severity ?? 0) - (best.main_kpi?.severity ?? 0);
    if (s !== 0) return s > 0 ? t : best;
    return t.order < best.order ? t : best;
  });
}
