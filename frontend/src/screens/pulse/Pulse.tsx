// Пульс (5.2): за 5 секунд видно, всё ли в порядке и куда нажать.
import { ArrowRight, CircleCheck, ShieldAlert, TrendingUp } from 'lucide-react';
import { Link } from 'react-router';
import { useClock, useGlossary, useMe, useOverview, useSeriesMany, useSources } from '../../api/hooks';
import type { Overview, Tile as TileT } from '../../api/types';
import { useGo, useLinkTo } from '../../app/nav';
import { countLabel, fmtNum, fmtShare } from '../../lib/format';
import { heaviestTileWithDeviation, priorityIndicators, pulseVerdict, shortTitle } from '../../lib/pulse';
import { KPI_STATUS, LEVEL_LABEL, asKpiStatus } from '../../lib/status';
import { addDaysToKey, dayKey, dayStartIso, fmtClock, fmtDay } from '../../lib/time';
import { Page } from '../../shell/Shell';
import { Tooltip } from '../../ui/Floating';
import { Provenance } from '../../ui/Provenance';
import { KpiLink, NodeLink } from '../../ui/Refs';
import { ErrorState, Skeleton } from '../../ui/States';
import { StatusGlyph, toneOf } from '../../ui/Status';
import { Tile } from '../../ui/Tile';
import s from './pulse.module.css';

const FORECAST_METHOD =
  'Прогноз — линейный тренд с недельной сезонностью по последним 28 суткам, коридор ±1σ. Простая модель без внешних данных.';

/** Куда ведёт плитка: есть открытые отклонения — карточка (или портфель по id), иначе Структура на главном KPI. */
function tileTarget(t: TileT): { path: string; params: Record<string, string | number> } | null {
  if (t.deviation_ids.length === 1) return { path: `/deviations/${t.deviation_ids[0]}`, params: {} };
  if (t.deviation_ids.length > 1) return { path: '/deviations', params: { ids: t.deviation_ids.join(',') } };
  const mk = t.main_kpi;
  if (!mk) return null;
  return { path: '/tree', params: { focus: mk.node_id, kpi: mk.kpi, panel: `kpi:${mk.node_id}:${mk.kpi}` } };
}

function HealthBar({ tiles }: { tiles: TileT[] }) {
  return (
    <div className={s.health} role="list" aria-label="Состояние процессов по порядку">
      {tiles.map((t) => {
        const st = t.kpis > 0 ? asKpiStatus(t.status) : 'unknown';
        const label = t.kpis > 0 ? KPI_STATUS[st].label : 'нет показателей в зоне';
        return (
          <Tooltip key={t.key} content={`${t.title}: ${label}`}>
            <span role="listitem" tabIndex={0} aria-label={`${t.title}: ${label}`} className={`${s.seg} ${s[`seg-${t.kpis > 0 ? toneOf(st) : 'none'}`]}`} />
          </Tooltip>
        );
      })}
    </div>
  );
}

function Verdict({ data }: { data: Overview }) {
  const tiles = [...data.tiles].sort((a, b) => a.order - b.order);
  const v = pulseVerdict(tiles);
  const ind = priorityIndicators(tiles);
  return (
    <section className={s.verdict} aria-label="Общая картина">
      <p className={s.sentence}>{v.sentence}</p>
      <HealthBar tiles={tiles} />
      <div className={s.priorities}>
        <span className={s.prioLead}>Приоритеты компании</span>
        {ind.map((i) => (
          <Tooltip key={i.priority} content={`Худший статус плиток: ${i.tiles.join(', ')}`}>
            <span className={`${s.prio} ${s[`prio-${toneOf(i.status)}`]}`} tabIndex={0}>
              <StatusGlyph glyph={KPI_STATUS[i.status].glyph} size={11} />
              <span className={s.prioName}>{i.label}</span>
              <span className={s.prioStatus}>{KPI_STATUS[i.status].label}</span>
            </span>
          </Tooltip>
        ))}
        {v.outOfZone > 0 ? (
          <span className={s.prioNote}>{countLabel(v.outOfZone, ['процесс', 'процесса', 'процессов'])} вне вашей зоны</span>
        ) : null}
      </div>
    </section>
  );
}

function Perspective({ tiles }: { tiles: TileT[] }) {
  const linkTo = useLinkTo();
  const risks = tiles
    .filter((t) => t.forecast_risk.at_risk && t.forecast_risk.node_id !== null && t.forecast_risk.kpi)
    .sort((a, b) => (a.forecast_risk.in_days ?? 99) - (b.forecast_risk.in_days ?? 99));
  return (
    <section className={`card ${s.panel}`} aria-labelledby="persp">
      <div className={s.panelHead}>
        <h2 id="persp">Перспектива на 14 дней</h2>
        <TrendingUp size={20} aria-hidden className="muted" />
      </div>
      {risks.length === 0 ? (
        <div className={s.noRisk}>
          <CircleCheck size={20} aria-hidden className={s.okIcon} />
          <span>В горизонте 14 дней рисков не видно</span>
        </div>
      ) : (
        <ul className={s.riskList}>
          {risks.map((t) => {
            const r = t.forecast_risk;
            const level = LEVEL_LABEL[r.level ?? ''] ?? r.level;
            return (
              <li key={t.key} className={s.risk}>
                <span className={`${s.riskDot} ${r.level === 'crit' ? s.riskCrit : s.riskWarn}`} aria-hidden />
                <div className={s.riskText}>
                  <b>{shortTitle(t.title)}:</b>{' '}
                  {typeof r.node_id === "number" && r.kpi ? (
                    <KpiLink nodeId={r.node_id} kpi={r.kpi}>
                      {r.title}
                    </KpiLink>
                  ) : (
                    r.title
                  )}{' '}
                  ({typeof r.node_id === "number" ? <NodeLink id={r.node_id}>{r.node_name}</NodeLink> : r.node_name}) пересечёт порог «{level}» через{' '}
                  <span className="num">{fmtNum(r.in_days ?? 0, 0)}</span>&nbsp;дн.{r.date ? ` (${fmtDay(r.date)})` : ''}
                </div>
                <Link
                  className="btn btn-outline btn-sm"
                  to={linkTo('/tree', { focus: r.node_id, kpi: r.kpi, panel: `kpi:${r.node_id}:${r.kpi}`, forecast: 14 })}
                >
                  Как предотвратить
                </Link>
              </li>
            );
          })}
        </ul>
      )}
      <p className={s.method}>{FORECAST_METHOD}</p>
    </section>
  );
}

function Decisions({ data }: { data: Overview }) {
  const linkTo = useLinkTo();
  const p = data.portfolio;
  const items: Array<{ label: string; value: string; tone?: string }> = [
    { label: 'Открыто', value: fmtNum(p.open, 0), tone: p.open > 0 ? 'crit' : undefined },
    { label: 'Просрочено', value: fmtNum(p.overdue, 0), tone: p.overdue > 0 ? 'crit' : undefined },
    { label: 'Проверено', value: fmtNum(p.verified, 0), tone: p.verified > 0 ? 'ok' : undefined },
    {
      label: 'Успешных перепроверок',
      value: p.recheck_success_rate === null || p.recheck_success_rate === undefined ? '—' : fmtShare(p.recheck_success_rate),
    },
  ];
  return (
    <Link to={linkTo('/deviations')} className={`card ${s.panel} ${s.decisions}`} aria-labelledby="dec">
      <div className={s.panelHead}>
        <h2 id="dec">Решения</h2>
        <ArrowRight size={20} aria-hidden />
      </div>
      <dl className={s.stats}>
        {items.map((i) => (
          <div key={i.label} className={s.stat}>
            <dt>{i.label}</dt>
            <dd className={i.tone ? s[`stat-${i.tone}`] : ''}>{i.value}</dd>
          </div>
        ))}
      </dl>
      <p className={s.method}>
        {p.total === 0
          ? 'Карточек решений в вашей зоне пока нет.'
          : p.recheck_success_rate === null || p.recheck_success_rate === undefined
            ? 'Доля успешных перепроверок появится после первой завершённой проверки.'
            : `Всего карточек: ${fmtNum(p.total, 0)}, перепроверок: ${fmtNum(p.rechecks, 0)}.`}
      </p>
    </Link>
  );
}

export function Pulse() {
  const me = useMe();
  const overview = useOverview();
  const clock = useClock();
  const sources = useSources();
  const glossary = useGlossary();
  const go = useGo();
  const linkTo = useLinkTo();

  const tiles = overview.data ? [...overview.data.tiles].sort((a, b) => a.order - b.order) : [];
  const today = clock.data?.today;
  const from = today ? dayStartIso(addDaysToKey(today, -14)) : undefined;
  const seriesQ = useSeriesMany(tiles.map((t) => (t.main_kpi && from ? { nodeId: t.main_kpi.node_id, kpi: t.main_kpi.kpi, from, agg: 'day' as const } : null)));

  const meData = me.data;
  const title = meData?.sees_everything
    ? 'Пульс компании'
    : `Пульс: ${meData?.scope_roots.map((r) => r.name).join(', ') ?? ''}`;
  const systems = sources.data?.filter((x) => x.kpis_in_zone > 0).length;
  const heavy = heaviestTileWithDeviation(tiles);
  const now = clock.data?.now ?? overview.data?.now;

  return (
    <Page>
      <div className={s.head}>
        <h1>{meData ? title : <Skeleton width={320} height={34} />}</h1>
        {now ? (
          <p className={s.sub}>
            {systems !== undefined ? `По данным ${countLabel(systems, ['системы', 'систем', 'систем'])}` : 'По данным систем компании'} · демо-время{' '}
            {fmtClock(now)}
            {overview.data && overview.data.units === 'relative' ? ' · значения в % к цели' : ''}
          </p>
        ) : null}
      </div>

      {overview.isError ? (
        <ErrorState error={overview.error} onRetry={() => overview.refetch()} />
      ) : !overview.data ? (
        <div className={s.loading}>
          <Skeleton height={150} radius={16} />
          <div className={s.grid}>
            {Array.from({ length: 8 }, (_, i) => (
              <Skeleton key={i} height={268} radius={16} />
            ))}
          </div>
        </div>
      ) : (
        <>
          <Verdict data={overview.data} />
          <section className={s.grid} aria-label="Процессы">
            {tiles.map((t, i) => {
              const target = tileTarget(t);
              const series = seriesQ[i]?.data ?? undefined;
              const metric = series?.metric ? glossary.data?.metrics?.[series.metric] : undefined;
              const isHeavy = heavy?.key === t.key && t.deviation_ids.length > 0;
              return (
                <Tile
                  key={t.key}
                  tile={t}
                  series={series ?? undefined}
                  seriesLoading={seriesQ[i]?.isPending && !!t.main_kpi}
                  openLabel={
                    t.deviation_ids.length
                      ? `${t.title}: открыть карточку ${t.deviation_ids.join(', ')}`
                      : `${t.title}: открыть в структуре`
                  }
                  onOpen={target ? () => go(target.path, target.params) : undefined}
                  provenance={
                    series && now ? (
                      <Provenance
                        compact
                        now={now}
                        sources={sources.data}
                        data={{
                          source: series.source,
                          points: series.points.length,
                          days: series.days,
                          valueDate: series.value_date,
                          stale: series.stale,
                          agg: series.agg,
                          profile: series.profile,
                          definition: metric?.definition,
                          formula: metric?.formula,
                          owner: metric?.owner,
                          extra: [['Спарклайн', `последние 14 суток до ${fmtDay(dayKey(now))}`]],
                        }}
                      />
                    ) : null
                  }
                  action={
                    isHeavy ? (
                      <Link className="btn btn-primary btn-sm" to={linkTo(`/deviations/${t.deviation_ids[0]}`)} onClick={(e) => e.stopPropagation()}>
                        <ShieldAlert size={16} aria-hidden />
                        Открыть карточку {t.deviation_ids[0]}
                      </Link>
                    ) : null
                  }
                />
              );
            })}
          </section>
          <div className={s.bottom}>
            <Perspective tiles={tiles} />
            <Decisions data={overview.data} />
          </div>
        </>
      )}
    </Page>
  );
}
