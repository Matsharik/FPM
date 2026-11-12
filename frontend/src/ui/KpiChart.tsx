// График KPI (3.6): факт (--text, 2 px), пороги пунктиром с подписями, вертикаль «сейчас»,
// прогноз с коридором и пересечениями, отметки сверху (событие, сигнал, решение, срок),
// окна перепроверки «до/после». Статус точек не вычисляем — только значения из API.
import { useMemo } from 'react';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip as RTooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { Flag, Forecast } from '../api/types';
import { fmtNum, fmtValue } from '../lib/format';
import { LEVEL_LABEL } from '../lib/status';
import { fmtDateTime, fmtDay, ms } from '../lib/time';

export interface ChartWindow {
  from: string;
  to: string;
  label: string;
}

export interface ChartMark {
  ts: string;
  kind: 'annotation' | 'signal' | 'decision' | 'due' | 'other';
  label: string;
  ref?: string | null;
}

const MARK_STYLE: Record<ChartMark['kind'], { fill: string; text: string; line: string }> = {
  annotation: { fill: '#e4e4e7', text: '#1c1c1e', line: '#a1a1aa' },
  signal: { fill: 'var(--crit)', text: '#fff', line: 'var(--crit)' },
  decision: { fill: 'var(--accent)', text: '#0a0a0a', line: '#0a0a0a' },
  due: { fill: '#fff', text: '#1c1c1e', line: '#0a0a0a' },
  other: { fill: '#f1f1f3', text: '#52525b', line: '#a1a1aa' },
};

/** Флажки ряда → отметки. kind info/warning/critical без ref — служебные, их не показываем. */
export function marksFromFlags(flags: Flag[] | undefined): ChartMark[] {
  return (flags ?? []).flatMap<ChartMark>((f) => {
    if (f.kind === 'annotation') return [{ ts: f.ts, kind: 'annotation', label: f.label ?? 'Событие', ref: f.ref }];
    if (f.kind === 'decision') return [{ ts: f.ts, kind: 'decision', label: 'Решение', ref: f.ref }];
    if (f.kind === 'critical' && f.ref?.startsWith('DEV-')) return [{ ts: f.ts, kind: 'signal', label: f.ref, ref: f.ref }];
    return [];
  });
}

interface Row {
  t: number;
  value?: number;
  fc?: number;
  band?: [number, number];
}

function MarkLabel({
  viewBox,
  mark,
  index,
  onClick,
}: {
  viewBox?: { x: number; y: number };
  mark: ChartMark;
  index: number;
  onClick?: (m: ChartMark) => void;
}) {
  if (!viewBox) return null;
  const st = MARK_STYLE[mark.kind];
  const text = mark.label.length > 22 ? mark.label.slice(0, 21) + '…' : mark.label;
  const w = Math.max(28, text.length * 6.6 + 14);
  const y = 2 + (index % 2) * 22;
  const x = Math.max(2, viewBox.x - w / 2);
  return (
    <g style={{ cursor: onClick ? 'pointer' : 'default' }} onClick={() => onClick?.(mark)} role={onClick ? 'button' : undefined}>
      <title>{mark.label}</title>
      <rect x={x} y={y} width={w} height={18} rx={9} fill={st.fill} stroke={mark.kind === 'due' || mark.kind === 'decision' ? '#0a0a0a' : 'none'} />
      <text x={x + w / 2} y={y + 13} textAnchor="middle" fontSize={11} fontWeight={600} fill={st.text}>
        {text}
      </text>
    </g>
  );
}

export function KpiChart({
  points,
  unit,
  thresholds,
  now,
  from,
  forecast,
  marks = [],
  windows = [],
  height = 260,
  onMark,
  currentStatusLabel,
}: {
  points: Array<{ ts: string; value: number }>;
  unit?: string | null;
  thresholds?: { target?: number | null; warn?: number | null; crit?: number | null } | null;
  now: string;
  from: string;
  forecast?: Forecast | null;
  marks?: ChartMark[];
  windows?: ChartWindow[];
  height?: number;
  onMark?: (m: ChartMark) => void;
  currentStatusLabel?: string;
}) {
  const nowMs = ms(now);
  const fromMs = ms(from);
  const data = useMemo<Row[]>(() => {
    const rows = new Map<number, Row>();
    for (const p of points) {
      const t = ms(p.ts);
      if (t < fromMs) continue;
      rows.set(t, { t, value: p.value });
    }
    if (forecast?.enough_data) {
      // Соединяем прогноз с последней точкой факта, чтобы пунктир начинался от неё.
      const last = points[points.length - 1];
      if (last) {
        const r = rows.get(ms(last.ts));
        if (r) {
          r.fc = last.value;
          r.band = [last.value, last.value];
        }
      }
      for (const p of forecast.points) {
        const t = ms(p.ts);
        const r = rows.get(t) ?? { t };
        r.fc = p.value;
        r.band = [p.lower, p.upper];
        rows.set(t, r);
      }
    }
    return [...rows.values()].sort((a, b) => a.t - b.t);
  }, [points, forecast, fromMs]);

  const lastT = data.length ? data[data.length - 1].t : nowMs;
  const domainX: [number, number] = [fromMs, Math.max(lastT, nowMs)];
  const th = thresholds ?? {};
  const vals = data.flatMap((r) => [r.value, r.fc, r.band?.[0], r.band?.[1]].filter((v): v is number => typeof v === 'number'));
  const thVals = [th.target, th.warn, th.crit].filter((v): v is number => typeof v === 'number');
  const all = [...vals, ...thVals];
  let lo = all.length ? Math.min(...all) : 0;
  let hi = all.length ? Math.max(...all) : 1;
  const pad = (hi - lo || Math.abs(hi) || 1) * 0.08;
  lo = lo - pad;
  hi = hi + pad;
  if (lo > 0 && Math.min(...(vals.length ? vals : [lo])) >= 0 && lo < (hi - lo) * 0.4) lo = 0;
  // «Круглые» деления оси: шаг 1·2·2,5·5 × 10^n
  const raw = (hi - lo) / 4;
  const mag = Math.pow(10, Math.floor(Math.log10(raw || 1)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((x) => x >= raw) ?? raw;
  lo = Math.floor(lo / step) * step;
  hi = Math.ceil(hi / step) * step;
  const ticks: number[] = [];
  for (let v = lo; v <= hi + step / 2; v += step) ticks.push(Number(v.toFixed(6)));

  const crossings = forecast?.enough_data
    ? (['warn', 'crit'] as const)
        .map((lvl) => ({ lvl, c: forecast.crossings?.[lvl] }))
        .filter((x) => x.c)
    : [];
  const visibleMarks = marks.filter((m) => ms(m.ts) >= domainX[0] && ms(m.ts) <= domainX[1]);
  const higherBetter = th.crit !== undefined && th.crit !== null && th.warn !== undefined && th.warn !== null && th.crit < th.warn;

  return (
    <div style={{ width: '100%', height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 52, right: 104, bottom: 4, left: 4 }}>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          {windows.map((w) => (
            <ReferenceArea
              key={w.label}
              x1={Math.max(ms(w.from), domainX[0])}
              x2={Math.min(ms(w.to), domainX[1])}
              fill={w.label.startsWith('до') ? '#a1a1aa' : '#1e9e55'}
              fillOpacity={0.1}
              label={{ value: w.label, position: 'insideBottom', fontSize: 12, fill: 'var(--text)' }}
            />
          ))}
          {th.warn !== null && th.warn !== undefined && th.crit !== null && th.crit !== undefined ? (
            <>
              <ReferenceArea y1={higherBetter ? th.crit : th.warn} y2={higherBetter ? th.warn : th.crit} fill="var(--warn)" fillOpacity={0.06} ifOverflow="hidden" />
              <ReferenceArea y1={higherBetter ? lo : th.crit} y2={higherBetter ? th.crit : hi} fill="var(--crit)" fillOpacity={0.06} ifOverflow="hidden" />
            </>
          ) : null}
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={domainX}
            tickFormatter={(t: number) => fmtDay(new Date(t).toISOString())}
            tick={{ fontSize: 12, fill: 'var(--text-muted)' }}
            tickLine={false}
            axisLine={{ stroke: 'var(--border-strong)' }}
            minTickGap={28}
          />
          <YAxis
            domain={[lo, hi]}
            ticks={ticks}
            tickFormatter={(v: number) => fmtNum(v)}
            tick={{ fontSize: 12, fill: 'var(--text-muted)' }}
            tickLine={false}
            axisLine={false}
            width={52}
            allowDataOverflow
          />
          {(
            [
              ['target', th.target, 'var(--ok-ink)'],
              ['warn', th.warn, 'var(--warn-ink)'],
              ['crit', th.crit, 'var(--crit-ink)'],
            ] as const
          ).map(([key, v, color]) =>
            v === null || v === undefined ? null : (
              <ReferenceLine
                key={key}
                y={v}
                stroke={color}
                strokeDasharray="5 4"
                strokeWidth={1.25}
                ifOverflow="extendDomain"
                label={{ value: `${key === 'target' ? 'цель' : LEVEL_LABEL[key]} ${fmtNum(v)}`, position: 'right', fontSize: 12, fill: color }}
              />
            ),
          )}
          {forecast?.enough_data ? (
            <Area dataKey="band" stroke="none" fill="#a1a1aa" fillOpacity={0.22} isAnimationActive={false} connectNulls />
          ) : null}
          {forecast?.enough_data ? (
            <Line dataKey="fc" stroke="var(--text)" strokeDasharray="6 4" strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />
          ) : null}
          <Line dataKey="value" stroke="var(--text)" strokeWidth={2} dot={false} activeDot={{ r: 5 }} isAnimationActive={false} connectNulls />
          <ReferenceLine x={nowMs} stroke="var(--ink)" strokeWidth={1.5} label={{ value: 'сейчас', position: 'insideTopRight', fontSize: 12, fill: 'var(--text)', offset: 4 }} />
          {crossings.map(({ lvl, c }) =>
            c && !c.already ? (
              <ReferenceLine
                key={lvl}
                x={ms(`${c.date}T00:00:00+03:00`)}
                stroke={lvl === 'crit' ? 'var(--crit)' : 'var(--warn)'}
                strokeDasharray="2 3"
                label={{ value: `${LEVEL_LABEL[lvl]} через ${c.in_days} дн.`, position: 'insideBottomLeft', fontSize: 12, fill: lvl === 'crit' ? 'var(--crit-ink)' : 'var(--warn-ink)' }}
              />
            ) : null,
          )}
          {visibleMarks.map((m, i) => (
            <ReferenceLine
              key={`${m.kind}-${m.ts}-${i}`}
              x={ms(m.ts)}
              stroke={MARK_STYLE[m.kind].line}
              strokeDasharray={m.kind === 'due' ? '4 3' : undefined}
              strokeWidth={m.kind === 'decision' ? 1.5 : 1}
              label={<MarkLabel mark={m} index={i} onClick={onMark} />}
            />
          ))}
          <RTooltip
            cursor={{ stroke: 'var(--text-muted)', strokeWidth: 1 }}
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null;
              const row = payload[0]?.payload as Row;
              const isLast = row.value !== undefined && row.t === ms(points[points.length - 1]?.ts ?? '');
              return (
                <div style={{ background: 'var(--ink)', color: '#fff', padding: '8px 10px', borderRadius: 8, fontSize: 12, lineHeight: 1.5 }}>
                  <div style={{ fontWeight: 600 }}>{fmtDay(new Date(label as number).toISOString())}</div>
                  {row.value !== undefined ? <div>Факт: {fmtValue(row.value, unit)}</div> : null}
                  {row.fc !== undefined && row.value === undefined ? (
                    <div>
                      Прогноз: {fmtValue(row.fc, unit)}
                      {row.band ? ` (${fmtNum(row.band[0])}–${fmtNum(row.band[1])})` : ''}
                    </div>
                  ) : null}
                  {isLast && currentStatusLabel ? <div>Статус сейчас: {currentStatusLabel}</div> : null}
                </div>
              );
            }}
          />
        </ComposedChart>
      </ResponsiveContainer>
      <span className="visually-hidden">График до {fmtDateTime(now)}</span>
    </div>
  );
}

/** Одна фраза о прогнозе из crossings, trend_per_day и direction. */
export function forecastPhrase(f: Forecast | null | undefined): string | null {
  if (!f) return null;
  if (!f.enough_data) return 'Недостаточно данных для прогноза (нужно не меньше 7 суток).';
  const parts: string[] = [];
  const c = f.crossings;
  if (c?.crit?.already) parts.push('порог «критично» уже пройден');
  else if (c?.crit) parts.push(`порог «критично» через ${c.crit.in_days} дн. (${fmtDay(c.crit.date)})`);
  else if (c?.warn?.already) parts.push('порог «внимание» уже пройден');
  else if (c?.warn) parts.push(`порог «внимание» через ${c.warn.in_days} дн. (${fmtDay(c.warn.date)})`);
  else parts.push(`в горизонте ${f.horizon} дн. пороги не пересекаются`);
  const t = f.trend_per_day;
  if (t !== null && t !== undefined && Math.abs(t) > 1e-9) {
    const worse = f.direction === 'lower_better' ? t > 0 : t < 0;
    const u = f.unit?.startsWith('%') ? 'п.п.' : f.unit ?? '';
    parts.push(`тренд — ${worse ? 'ухудшение' : 'улучшение'} на ${fmtNum(Math.abs(t))}${u ? ' ' + u : ''} в сутки`);
  }
  const s = parts.join('; ');
  return s.charAt(0).toUpperCase() + s.slice(1) + '.';
}
