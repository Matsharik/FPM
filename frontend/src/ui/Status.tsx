import { ArrowUp, Check, CheckCheck, Clock3, Minus, TriangleAlert, X } from 'lucide-react';
import type { DeviationStatus, StageStatus } from '../api/types';
import { DEVIATION_STATUS, KPI_STATUS, STAGE_STATUS, asKpiStatus, type Glyph, type StatusMeta, type Tone } from '../lib/status';
import s from './ui.module.css';

const ICONS: Record<Glyph, typeof Check | null> = {
  check: Check,
  alert: TriangleAlert,
  cross: X,
  dash: Minus,
  'double-check': CheckCheck,
  up: ArrowUp,
  clock: Clock3,
  dot: null,
};

export function StatusGlyph({ glyph, size = 12 }: { glyph: Glyph; size?: number }) {
  const Icon = ICONS[glyph];
  return (
    <span className={s.glyph} aria-hidden>
      {Icon ? <Icon size={size} strokeWidth={3} /> : <span style={{ width: 6, height: 6, borderRadius: 3, background: '#fff' }} />}
    </span>
  );
}

function Badge({ meta, size, label }: { meta: StatusMeta; size?: 'sm' | 'md'; label?: string }) {
  return (
    <span className={`${s.badge} ${size === 'sm' ? s.badgeSm : ''} ${s[`tone-${meta.tone}`]}`}>
      <StatusGlyph glyph={meta.glyph} size={size === 'sm' ? 10 : 12} />
      {label ?? meta.label}
    </span>
  );
}

/** Статус KPI или плитки: Норма / Внимание / Критично / Нет данных. */
export function StatusBadge({ status, size, label }: { status: string | null | undefined; size?: 'sm' | 'md'; label?: string }) {
  return <Badge meta={KPI_STATUS[asKpiStatus(status)]} size={size} label={label} />;
}

export function DeviationStatusBadge({ status, size }: { status: string; size?: 'sm' | 'md' }) {
  const meta = DEVIATION_STATUS[status as DeviationStatus] ?? { label: status, tone: 'unknown', glyph: 'dash' };
  return <Badge meta={meta} size={size} />;
}

export function StageStatusBadge({ status, size }: { status: string; size?: 'sm' | 'md' }) {
  const meta = STAGE_STATUS[status as StageStatus] ?? { label: status, tone: 'unknown', glyph: 'dash' };
  return <Badge meta={meta} size={size} />;
}

export function StatusDot({ tone, title }: { tone: Tone; title?: string }) {
  return <span className={`${s.dot} ${s[`dot-${tone}`]}`} title={title} aria-label={title} role={title ? 'img' : undefined} />;
}

export function toneOf(status: string | null | undefined): Tone {
  return KPI_STATUS[asKpiStatus(status)].tone;
}

export function inkClass(tone: Tone): string {
  return s[`ink-${tone}`] ?? '';
}
