// «Что изменилось» после перемотки демо-времени (5.15): только то, что реально изменилось по снимкам.
import { fmtValue } from './format';
import { KPI_STATUS, asKpiStatus } from './status';

interface TileSnap {
  key: string;
  title: string;
  status: string;
  main_kpi?: { node_id: number; kpi: string; title: string; value?: number | null; unit?: string | null } | null;
  deviation_ids: string[];
}

export interface OverviewSnap {
  now: string;
  tiles: TileSnap[];
  portfolio: { open: number; overdue: number; verified: number; failed: number };
}

export interface ChangeItem {
  kind: 'tile' | 'portfolio' | 'new_deviation' | 'recheck_ready';
  text: string;
  /** Куда ведёт пункт: плитка — структура/карточка, карточка — /deviations/ID. */
  link?: { path: string; params?: Record<string, string | number> };
}

export function diffOverview(before: OverviewSnap, after: OverviewSnap): ChangeItem[] {
  const out: ChangeItem[] = [];
  const prev = new Map(before.tiles.map((t) => [t.key, t]));
  for (const t of after.tiles) {
    const b = prev.get(t.key);
    if (!b) continue;
    const parts: string[] = [];
    if (asKpiStatus(b.status) !== asKpiStatus(t.status)) {
      parts.push(`${KPI_STATUS[asKpiStatus(b.status)].label} → ${KPI_STATUS[asKpiStatus(t.status)].label}`);
    }
    const bm = b.main_kpi;
    const am = t.main_kpi;
    // Значение сравниваем, только если главный KPI плитки тот же.
    if (bm && am && bm.node_id === am.node_id && bm.kpi === am.kpi && bm.value !== am.value && parts.length) {
      parts.push(`${am.title}: ${fmtValue(bm.value, bm.unit)} → ${fmtValue(am.value, am.unit)}`);
    }
    if (parts.length) {
      out.push({
        kind: 'tile',
        text: `${t.title}: ${parts.join('; ')}`,
        link: am ? { path: '/tree', params: { focus: am.node_id, kpi: am.kpi, panel: `kpi:${am.node_id}:${am.kpi}` } } : undefined,
      });
    }
  }
  const p0 = before.portfolio;
  const p1 = after.portfolio;
  const pp: string[] = [];
  if (p0.open !== p1.open) pp.push(`открыто ${p0.open} → ${p1.open}`);
  if (p0.overdue !== p1.overdue) pp.push(`просрочено ${p0.overdue} → ${p1.overdue}`);
  if (p0.verified !== p1.verified) pp.push(`проверено ${p0.verified} → ${p1.verified}`);
  if (p0.failed !== p1.failed) pp.push(`не сработало ${p0.failed} → ${p1.failed}`);
  if (pp.length) out.push({ kind: 'portfolio', text: `Решения: ${pp.join(', ')}`, link: { path: '/deviations' } });
  return out;
}

export interface DevLite {
  id: string;
  title: string;
  node_name: string;
  status: string;
  action?: { assigned_at?: string | null } | null;
}

/** Карточки, которые теперь можно перепроверять: действие назначено не меньше minDays назад. */
export function readyForRecheck(devs: DevLite[], nowIso: string, minDays: number): DevLite[] {
  const now = Date.parse(nowIso);
  return devs.filter((d) => {
    if (!['assigned', 'in_progress', 'done'].includes(d.status)) return false;
    const at = d.action?.assigned_at;
    return !!at && (now - Date.parse(at)) / 86_400_000 >= minDays;
  });
}
