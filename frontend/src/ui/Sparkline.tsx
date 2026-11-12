// Спарклайн: одна линия факта (--text, 2 px), точка «сейчас», бледная зона хуже порога «внимание».
// Без осей — это глиф рядом с крупным значением; подробный график — KpiChart (Ф2).
import { useId } from 'react';
import { fmtDay } from '../lib/time';
import { fmtValue } from '../lib/format';
import { useWidth } from './useWidth';

export interface SparkPoint {
  ts: string;
  value: number;
}

export function Sparkline({
  points,
  unit,
  warn,
  direction,
  height = 44,
  tone = 'ink',
  label,
}: {
  points: SparkPoint[];
  unit?: string | null;
  warn?: number | null;
  direction?: string | null;
  height?: number;
  tone?: 'ink' | 'crit' | 'warn';
  label?: string;
}) {
  const clipId = useId();
  const [ref, W] = useWidth<HTMLDivElement>();
  if (points.length < 2) {
    return <div ref={ref} style={{ height }} aria-hidden />;
  }
  const H = height;
  const pad = 4;
  const vals = points.map((p) => p.value);
  let min = Math.min(...vals);
  let max = Math.max(...vals);
  if (warn !== null && warn !== undefined) {
    // порог показываем, только если он рядом с данными — иначе спарклайн сплющится
    const span = max - min || Math.abs(max) || 1;
    if (warn >= min - span * 0.5 && warn <= max + span * 0.5) {
      min = Math.min(min, warn);
      max = Math.max(max, warn);
    }
  }
  if (max === min) {
    max += 1;
    min -= 1;
  }
  const x = (i: number) => pad + (i / (points.length - 1)) * (W - pad * 2);
  const y = (v: number) => pad + (1 - (v - min) / (max - min)) * (H - pad * 2);
  const d = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ');
  const last = points[points.length - 1];
  const stroke = 'var(--text)';
  const dotFill = tone === 'crit' ? 'var(--crit)' : tone === 'warn' ? 'var(--warn)' : 'var(--text)';
  const warnY = warn !== null && warn !== undefined && warn >= min && warn <= max ? y(warn) : null;
  const badAbove = direction !== 'higher_better';
  const title =
    label ??
    `${fmtDay(points[0].ts)} — ${fmtDay(last.ts)}: от ${fmtValue(Math.min(...vals), unit)} до ${fmtValue(Math.max(...vals), unit)}`;
  return (
    <div ref={ref} style={{ height: H }}>
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={title} style={{ display: 'block' }}>
      <title>{title}</title>
      {warnY !== null ? (
        <>
          <clipPath id={clipId}>
            <rect x={0} y={badAbove ? 0 : warnY} width={W} height={badAbove ? warnY : H - warnY} />
          </clipPath>
          <rect x={0} y={0} width={W} height={H} fill="var(--warn)" opacity={0.08} clipPath={`url(#${clipId})`} />
          <line x1={0} x2={W} y1={warnY} y2={warnY} stroke="var(--warn)" strokeWidth={1} strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />
        </>
      ) : null}
      <path d={d} fill="none" stroke={stroke} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      <circle cx={x(points.length - 1)} cy={y(last.value)} r={3.5} fill={dotFill} stroke="var(--surface)" strokeWidth={1.5} />
    </svg>
    </div>
  );
}
