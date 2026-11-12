// Паспорт данных (7.1): откуда цифры и насколько они свежие — относительно демо-часов.
import { Database } from 'lucide-react';
import { Link } from 'react-router';
import { useLinkTo } from '../app/nav';
import { fmtNum, plural } from '../lib/format';
import { dayDiff, dayKey, fmtDay, relativeDay } from '../lib/time';
import { Popover } from './Floating';
import s from './ui.module.css';

export interface SourceInfo {
  key: string;
  title: string;
  system: string;
  mode?: string | null;
  read_only?: boolean | null;
  connector: string;
}

export interface ProvenanceData {
  source?: string | null;
  points?: number | null;
  days?: number | null;
  valueDate?: string | null;
  stale?: boolean | null;
  agg?: string | null;
  profile?: string | null;
  definition?: string | null;
  formula?: string | null;
  owner?: string | null;
  extra?: Array<[string, string]>;
}

type Freshness = { label: string; tone: 'ok' | 'warn' | 'crit' };

export function freshness(valueDate: string | null | undefined, stale: boolean | null | undefined, nowIso: string): Freshness | null {
  if (!valueDate) return null;
  if (stale) return { label: 'устарело', tone: 'crit' };
  const diff = dayDiff(dayKey(valueDate), dayKey(nowIso));
  return diff <= 1 ? { label: 'свежо', tone: 'ok' } : { label: 'устаревает', tone: 'warn' };
}

const AGG: Record<string, string> = { day: 'по суткам', raw: 'исходные точки' };
const PROFILE: Record<string, string> = { default: 'обычный', season: 'сезон' };

export function Provenance({
  data,
  sources,
  now,
  compact,
}: {
  data: ProvenanceData;
  sources: SourceInfo[] | undefined;
  now: string;
  compact?: boolean;
}) {
  const linkTo = useLinkTo();
  const src = sources?.find((x) => x.key === data.source);
  const sys = src ? src.system : data.source ?? 'источник не указан';
  const fresh = freshness(data.valueDate, data.stale, now);
  const updated = data.valueDate ? `обновлено ${fmtDay(data.valueDate)} (${relativeDay(data.valueDate, now)})` : 'данных нет';
  const parts = compact
    ? [sys, data.valueDate ? fmtDay(data.valueDate) : 'нет данных']
    : [
        sys,
        src?.mode === 'mock' ? 'демо-данные' : null,
        data.points !== undefined && data.points !== null
          ? `${fmtNum(data.points, 0)} ${plural(data.points, ['точка', 'точки', 'точек'])} за период`
          : null,
        data.days ? `история ${fmtNum(data.days, 0)} дн.` : null,
        updated,
      ].filter(Boolean);
  return (
    <Popover
      trigger={
        <button type="button" className={s.prov} aria-label="Паспорт данных">
          <Database size={12} aria-hidden />
          <span className={s.provText}>{parts.join(' · ')}</span>
        </button>
      }
    >
      <div className={s.popTitle}>Паспорт данных</div>
      <dl className={s.provList}>
        <dt>Система</dt>
        <dd>
          {src ? (
            <Link to={linkTo('/sources', { source: src.key })}>
              {src.title} ({src.system})
            </Link>
          ) : (
            sys
          )}
        </dd>
        {src ? (
          <>
            <dt>Режим</dt>
            <dd>
              {src.mode === 'mock' ? 'демо-данные' : src.mode}
              {src.read_only ? ', только чтение' : ''}
            </dd>
            <dt>Подключение</dt>
            <dd>{src.connector}</dd>
          </>
        ) : null}
        {data.points !== undefined && data.points !== null ? (
          <>
            <dt>Точек в периоде</dt>
            <dd>{fmtNum(data.points, 0)}</dd>
          </>
        ) : null}
        {data.days ? (
          <>
            <dt>История</dt>
            <dd>{fmtNum(data.days, 0)} дн.</dd>
          </>
        ) : null}
        <dt>Последнее значение</dt>
        <dd>
          {data.valueDate ? `${fmtDay(data.valueDate)} (${relativeDay(data.valueDate, now)})` : 'нет данных'}
          {fresh ? ` · ${fresh.label}` : ''}
        </dd>
        {data.agg ? (
          <>
            <dt>Агрегация</dt>
            <dd>{AGG[data.agg] ?? data.agg}</dd>
          </>
        ) : null}
        {data.profile ? (
          <>
            <dt>Пороги</dt>
            <dd>профиль «{PROFILE[data.profile] ?? data.profile}»</dd>
          </>
        ) : null}
        {data.definition ? (
          <>
            <dt>Определение</dt>
            <dd>{data.definition}</dd>
          </>
        ) : null}
        {data.formula ? (
          <>
            <dt>Формула</dt>
            <dd>{data.formula}</dd>
          </>
        ) : null}
        {data.owner ? (
          <>
            <dt>Владелец метрики</dt>
            <dd>{data.owner}</dd>
          </>
        ) : null}
        {data.extra?.map(([k, v]) => (
          <span key={k} style={{ display: 'contents' }}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </span>
        ))}
      </dl>
    </Popover>
  );
}
