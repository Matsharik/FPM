import { ArrowDownRight, ArrowRight, ArrowUpRight } from 'lucide-react';
import { fmtDelta, fmtNum } from '../lib/format';
import { trendTone } from '../lib/status';
import { inkClass } from './Status';
import s from './ui.module.css';

/** Значение + единица (единица — из ответа API). */
export function KpiValue({
  value,
  unit,
  size = 'md',
  maxFrac,
}: {
  value: number | null | undefined;
  unit?: string | null;
  size?: 'sm' | 'md' | 'lg' | 'xl';
  maxFrac?: number;
}) {
  const n = fmtNum(value, maxFrac);
  return (
    <span className={`${s.kpiValue} ${s[`size-${size}`]}`}>
      <span>{n}</span>
      {n !== '—' && unit ? <span className={s.unit}>{unit}</span> : null}
    </span>
  );
}

/** Изменение за неделю: стрелка и цвет — по trend / trend_quality из ответа. */
export function Delta({
  value,
  unit,
  trend,
  quality,
  status,
  note,
}: {
  value: number | null | undefined;
  unit?: string | null;
  trend?: string | null;
  quality?: string | null;
  status?: string | null;
  note?: string;
}) {
  if (value === null || value === undefined) return null;
  const Icon = trend === 'up' ? ArrowUpRight : trend === 'down' ? ArrowDownRight : ArrowRight;
  return (
    <span className={`${s.delta} ${inkClass(trendTone(quality, status))}`}>
      <Icon size={16} strokeWidth={2.5} aria-hidden />
      {fmtDelta(value, unit)}
      {note ? <span className={s.deltaNote}>{note}</span> : null}
    </span>
  );
}
