// Плитка Пульса — презентационная: данные (ряд для спарклайна, паспорт) передаёт контейнер.
import { CircleAlert, TrendingUp } from 'lucide-react';
import type { ReactNode } from 'react';
import type { KpiSeries, Tile as TileT } from '../api/types';
import { countLabel } from '../lib/format';
import { LEVEL_LABEL } from '../lib/status';
import { fmtDay } from '../lib/time';
import { KpiLink, NodeLink } from './Refs';
import { Sparkline } from './Sparkline';
import { Skeleton } from './States';
import { StatusBadge, toneOf } from './Status';
import { Delta, KpiValue } from './Values';
import s from './ui.module.css';

export function Tile({
  tile,
  series,
  seriesLoading,
  provenance,
  action,
  onOpen,
  openLabel,
}: {
  tile: TileT;
  series?: KpiSeries;
  seriesLoading?: boolean;
  provenance?: ReactNode;
  action?: ReactNode;
  onOpen?: () => void;
  openLabel?: string;
}) {
  const tone = toneOf(tile.status);
  const mk = tile.main_kpi;
  if (!mk || tile.kpis === 0) {
    return (
      <div className={`${s.tile} ${s.tileEmpty}`} aria-label={`${tile.title}: нет показателей в вашей зоне`}>
        <div className={s.tileHead}>
          <div className={s.tileTitle}>{tile.title}</div>
          <StatusBadge status="unknown" size="sm" />
        </div>
        <div className={s.tileEmptyText}>В вашей зоне нет показателей этого процесса</div>
      </div>
    );
  }
  const risk = tile.forecast_risk;
  const openDev = tile.open_deviations ?? 0;
  const handleKey = (e: React.KeyboardEvent) => {
    if (e.target !== e.currentTarget) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onOpen?.();
    }
  };
  return (
    <div
      className={`${s.tile} ${s[`tile-${tone}`] ?? ''}`}
      role="button"
      tabIndex={0}
      aria-label={openLabel ?? tile.title}
      onClick={onOpen}
      onKeyDown={handleKey}
    >
      <div className={s.tileHead}>
        <div className={s.tileTitle}>{tile.title}</div>
        <StatusBadge status={tile.status} size="sm" />
      </div>
      <div className={s.tileKpiTitle}>
        <KpiLink nodeId={mk.node_id} kpi={mk.kpi}>
          {mk.title}
        </KpiLink>{' '}
        ·{' '}
        <NodeLink id={mk.node_id}>{mk.node_name}</NodeLink>
      </div>
      <div className={s.tileValueRow}>
        <KpiValue value={mk.value} unit={mk.unit} size="lg" />
        <Delta value={mk.delta_week} unit={mk.unit} trend={mk.trend} quality={mk.trend_quality} status={mk.status} note="за 7 дн." />
      </div>
      {action ? <div>{action}</div> : null}
      <div className={s.tileSpark}>
        {series ? (
          <Sparkline
            points={series.points}
            unit={series.unit}
            warn={series.thresholds?.warn ?? null}
            direction={series.direction}
            tone={tone === 'crit' ? 'crit' : tone === 'warn' ? 'warn' : 'ink'}
          />
        ) : seriesLoading ? (
          <Skeleton height={44} />
        ) : null}
      </div>
      {provenance}
      <div className={s.tileFoot}>
        {openDev > 0 ? (
          <span className={`${s.pill} ${s.pillCrit}`}>
            <CircleAlert size={14} aria-hidden />
            {countLabel(openDev, ['открытое решение', 'открытых решения', 'открытых решений'])}
          </span>
        ) : null}
        {risk.at_risk && risk.in_days !== null && risk.in_days !== undefined ? (
          <span className={`${s.pill} ${s.pillWarn}`} title={risk.date ? `${LEVEL_LABEL[risk.level ?? ''] ?? risk.level} · ${fmtDay(risk.date)}` : undefined}>
            <TrendingUp size={14} aria-hidden />
            Риск через {risk.in_days}&nbsp;дн.
          </span>
        ) : null}
      </div>
    </div>
  );
}
