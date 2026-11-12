// Карточка отклонения (5.6) — главный экран приёмки: Сигнал → Контекст → Причина → Действие → Проверка.
import { AlarmClock, ArrowRight, Crosshair, FastForward, RefreshCw, ShieldAlert } from 'lucide-react';
import { EyesOfRole } from '../../ui/EyesOfRole';
import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router';
import { ApiError, api } from '../../api/client';
import { useAdvanceWithChanges, useDeviation, useDone, usePatchDeviation, useRecheck, useSuggest, type PatchBody } from '../../api/deviationHooks';
import { useAudit, useClock, useForecast, useGraph, useMe, useOverview, useSeries, useUsers } from '../../api/hooks';
import type { Deviation, KpiSeries, TraceStep } from '../../api/types';
import { useLinkTo } from '../../app/nav';
import { auditAction } from '../../lib/audit';
import { fmtNum, fmtShare, fmtValue, plural } from '../../lib/format';
import { indexGraph, type GraphLike } from '../../lib/graph';
import { impactUp } from '../../lib/impact';
import { can } from '../../lib/permissions';
import { DEVIATION_STATUS, LEVEL_LABEL } from '../../lib/status';
import { MIN_RECHECK_DAYS, TRANSITIONS, chainStep, needsAction } from '../../lib/transitions';
import { addDaysToKey, dayKey, dayStartIso, daysBetween, fmtDateTime, fmtDay } from '../../lib/time';
import { Page } from '../../shell/Shell';
import { ChainStepper, type ChainKey } from '../../ui/ChainStepper';
import { ConfirmDialog } from '../../ui/ConfirmDialog';
import { KpiChart, forecastPhrase, type ChartWindow } from '../../ui/KpiChart';
import { DevRef, KpiLink, KpiRef, NodeLink, NodeRef, OrderRef } from '../../ui/Refs';
import { ErrorState, OutOfZone, Skeleton } from '../../ui/States';
import { DeviationStatusBadge, StatusBadge, StatusDot, toneOf } from '../../ui/Status';
import { toast } from '../../ui/Toast';
import { KpiValue } from '../../ui/Values';
import { chartMarks } from '../../inspector/KpiBlock';
import { traceVerdict } from '../tree/TraceStrip';
import s from './deviation.module.css';

type Recheck = Deviation['rechecks'][number];

const CONFIDENCE: Record<string, string> = { high: 'высокая', medium: 'средняя', low: 'низкая' };
const PROFILE: Record<string, string> = { default: 'обычные пороги', season: 'сезонные пороги' };
const RULE: Record<string, string> = { improvement: 'улучшение не меньше 50 %', target: 'показатель вернулся к цели' };
const DIM: Record<string, string> = { product_line: 'Линейка', brand: 'Бренд', segment: 'Сегмент' };

function Section({ id, n, title, current, children, extra }: { id: ChainKey; n: number; title: string; current: boolean; children: React.ReactNode; extra?: React.ReactNode }) {
  return (
    <section id={id} className={`${s.section} ${current ? s.sectionCurrent : ''}`} aria-labelledby={`${id}-h`}>
      <div className={s.sectionHead}>
        <span className={s.stepNo}>{n}</span>
        <h2 id={`${id}-h`}>{title}</h2>
        <span style={{ flex: 1 }} />
        {extra}
      </div>
      {children}
    </section>
  );
}

function lastCompleted(rechecks: Recheck[]): Recheck | undefined {
  return [...rechecks].reverse().find((r) => r.result === 'passed' || r.result === 'failed');
}

function recheckWindows(r: Recheck | undefined, unit: string | null | undefined): ChartWindow[] {
  if (!r?.baseline || !r.after) return [];
  return [
    { from: r.baseline.from, to: r.baseline.to, label: `до ${fmtValue(r.baseline.value, unit)}` },
    { from: r.after.from, to: r.after.to, label: `после ${fmtValue(r.after.value, unit)}` },
  ];
}

/** Флажок решения на рядах сигнала и первопричины (если такого флажка с этим ref ещё нет). */
async function placeDecisionFlags(d: Deviation, label: string, nowIso: string, today: string) {
  const targets = new Map<string, { node: number; kpi: string }>();
  targets.set(`${d.node_id}:${d.kpi}`, { node: d.node_id, kpi: d.kpi });
  const root = d.cause?.root;
  if (root?.kpi) targets.set(`${root.node_id}:${root.kpi}`, { node: root.node_id, kpi: root.kpi });
  let placed = 0;
  for (const t of targets.values()) {
    try {
      const series = await api<KpiSeries>(`/api/kpi/${t.node}/${t.kpi}`, { query: { from: dayStartIso(addDaysToKey(today, -1)), agg: 'day' } });
      if ((series.flags ?? []).some((f) => f.kind === 'decision' && f.ref === d.id)) continue;
      await api(`/api/qc/kpi/${t.node}/${t.kpi}/flags`, { method: 'POST', body: { ts: nowIso, kind: 'decision', label, ref: d.id } });
      placed++;
    } catch {
      // Ряд вне зоны или нет права flags.write — метку нарисуем по action.assigned_at.
    }
  }
  return placed;
}

export function DeviationCard() {
  const { id = '' } = useParams();
  const q = useDeviation(id);
  const linkTo = useLinkTo();

  if (q.isError) {
    const e = q.error;
    return (
      <Page>
        <h1 style={{ marginBottom: 16 }}>Карточка {id}</h1>
        {e instanceof ApiError && e.code === 'out_of_zone' ? (
          <OutOfZone what={`Карточка ${id} и её узлы`} />
        ) : (
          <ErrorState error={e} onRetry={() => q.refetch()} back={<Link className="btn btn-outline btn-sm" to={linkTo('/deviations')}>К списку решений</Link>} />
        )}
      </Page>
    );
  }
  if (!q.data) {
    return (
      <Page>
        <Skeleton height={40} width={480} />
        <div style={{ height: 16 }} />
        <Skeleton height={320} radius={16} />
      </Page>
    );
  }
  return <CardBody d={q.data} />;
}

function CardBody({ d }: { d: Deviation }) {
  const me = useMe();
  const clock = useClock();
  const users = useUsers();
  const graph = useGraph();
  const overview = useOverview();
  const linkTo = useLinkTo();
  const perms = me.data?.permissions;
  const canManage = can(perms, 'deviations.manage');
  const canRecheck = can(perms, 'deviations.recheck');
  const canDemo = can(perms, 'demo.control');
  const idx = useMemo(() => (graph.data ? indexGraph(graph.data as unknown as GraphLike) : null), [graph.data]);
  const signalNode = idx?.byId.get(d.node_id);
  const signalVisible = !!signalNode?.clickable && d.signal.value !== null && d.signal.value !== undefined;
  const now = clock.data?.now ?? d.created_at;
  const today = clock.data?.today ?? dayKey(d.created_at);

  const chartFrom = dayStartIso(addDaysToKey(today, -30));
  const series = useSeries(signalVisible ? { nodeId: d.node_id, kpi: d.kpi, from: chartFrom, agg: 'day' } : null);
  const forecast = useForecast(signalVisible ? d.node_id : null, d.kpi, 14);
  const audit = useAudit({ object_id: d.id, limit: 30 });
  const step = chainStep(d.status);
  const userName = (login: string | null | undefined) => users.data?.find((u) => u.login === login)?.name ?? login ?? '—';
  const unit = d.cause?.trace?.[0]?.unit ?? series.data?.unit ?? null;
  const done = lastCompleted(d.rechecks ?? []);

  const scrollTo = (k: ChainKey) => document.getElementById(k)?.scrollIntoView({ behavior: 'smooth', block: 'start' });

  const tileTitle = overview.data?.tiles.find((t) => t.key === d.context?.tile)?.title ?? d.context?.tile;
  const impact = idx ? impactUp(idx, d.node_id, d.kpi) : [];
  const rootImpact = idx && d.cause?.root?.kpi ? impactUp(idx, d.cause.root.node_id, d.cause.root.kpi) : [];
  const impactTiles = new Set<string>();
  const impactStages = new Set<number>();
  for (const i of [...impact, ...rootImpact]) {
    const n = idx?.byId.get(i.nodeId);
    if (n?.tile) impactTiles.add(n.tile);
    if (n?.stage) impactStages.add(n.stage);
  }
  const tileName = (key: string) => overview.data?.tiles.find((t) => t.key === key)?.title ?? key;

  return (
    <Page>
      <header className={s.head}>
        <div>
          <div className={s.kicker}>
            {d.id} · создана {fmtDateTime(d.created_at)} · {d.signal.detected_by === 'auto' ? 'обнаружена автоматически' : 'создана вручную'}
          </div>
          <div className={s.titleRow}>
            <h1>
              <KpiLink nodeId={d.node_id} kpi={d.kpi} clickable={!!signalNode?.clickable}>
                {d.title}
              </KpiLink>{' '}
              ·{' '}
              <NodeLink id={d.node_id} clickable={!!signalNode?.clickable} owner={signalNode?.owner}>
                {d.node_name}
              </NodeLink>
            </h1>
            <DeviationStatusBadge status={d.status} />
            {d.overdue ? (
              <span className={s.overdue}>
                <AlarmClock size={16} aria-hidden />
                Срок действия прошёл
              </span>
            ) : null}
          </div>
        </div>
        <EyesOfRole />
      </header>

      <div className={s.chain}>
        <ChainStepper current={step} onStep={scrollTo} />
      </div>

      <div className={s.grid}>
        {/* 1. Сигнал */}
        <Section id="signal" n={1} title="Сигнал" current={false}>
          <div className={s.cols}>
            <div>
              {signalVisible ? (
                <div className={s.big}>
                  <KpiValue value={d.signal.value} unit={unit} size="xl" />
                  <span className={s.vs}>
                    при пороге «{LEVEL_LABEL[d.signal.level ?? ''] ?? d.signal.level}» {fmtValue(d.signal.threshold, unit)}
                  </span>
                  <StatusBadge status={d.signal.status} />
                </div>
              ) : (
                <OutOfZone owner={signalNode?.owner} what={`Цифры сигнала «${d.title}» (${d.node_name})`} />
              )}
              <dl className={s.facts}>
                <dt>Показатель</dt>
                <dd>
                  {signalNode?.clickable ? <KpiRef nodeId={d.node_id} kpi={d.kpi} title={d.title} nodeName={d.node_name} /> : `${d.node_name}: ${d.title}`}
                </dd>
                <dt>Обнаружено</dt>
                <dd>
                  {d.signal.detected_by === 'auto' ? 'автоматически' : 'вручную'} · {fmtDateTime(d.signal.ts)} {d.signal.day ? ` (сутки ${fmtDay(d.signal.day)})` : null}
                </dd>
              </dl>
            </div>
            <div className={s.now}>
              <div className={s.nowLabel}>Сейчас{d.current?.value_date ? ` · ${fmtDay(d.current.value_date)}` : ''}</div>
              {d.current?.value !== null && d.current?.value !== undefined ? (
                <div className={s.big}>
                  <KpiValue value={d.current.value} unit={unit} size="lg" />
                  <StatusBadge status={d.current.status} size="sm" />
                </div>
              ) : (
                <div className={s.big}>
                  <StatusBadge status={d.current?.status} />
                  <span className="muted">значение вне вашей зоны</span>
                </div>
              )}
              {signalVisible && d.current?.value !== null && d.current?.value !== undefined ? (
                <div className="muted" style={{ marginTop: 6 }}>
                  при сигнале было {fmtValue(d.signal.value, unit)}
                </div>
              ) : null}
            </div>
          </div>
          {signalVisible ? (
            <>
              <div style={{ marginTop: 16 }}>
                {series.data ? (
                  <KpiChart
                    points={series.data.points}
                    unit={series.data.unit}
                    thresholds={series.data.thresholds}
                    now={now}
                    from={chartFrom}
                    forecast={forecast.data}
                    marks={chartMarks(series.data.flags, [d])}
                    windows={recheckWindows(done, series.data.unit)}
                    height={280}
                  />
                ) : (
                  <Skeleton height={280} />
                )}
              </div>
              {forecast.data ? (
                <div className={`${s.phrase} ${d.status === 'verified' ? s.phraseNeutral : ''}`}>Если ничего не делать: {forecastPhrase(forecast.data)}</div>
              ) : null}
            </>
          ) : null}
        </Section>

        {/* 2. Контекст */}
        <Section id="context" n={2} title="Контекст" current={false}>
          <div className={s.cols}>
            <div>
              <div className={s.chips}>
                {tileTitle ? <span className={s.chip}>Плитка: {tileTitle}</span> : null}
                {d.context?.stage ? (
                  <Link className={s.chip} to={linkTo('/orders', { stage: d.context.stage })}>
                    Этап потока {d.context.stage}
                  </Link>
                ) : null}
                <span className={s.chip}>{PROFILE[d.context?.season_profile ?? 'default'] ?? d.context?.season_profile}</span>
                {Object.entries(d.context?.dims ?? {}).map(([k, v]) => (
                  <span key={k} className={s.chip}>
                    {DIM[k] ?? k}: {String(v)}
                  </span>
                ))}
                {d.context?.window ? (
                  <span className={s.chip}>
                    окно {fmtDay(d.context.window.from)} — {fmtDay(addDaysToKey(dayKey(d.context.window.to), -1))}
                  </span>
                ) : null}
              </div>
              <div className={s.sub}>На что влияет</div>
              {impact.length === 0 ? (
                <p className="muted">Выше по структуре на этот показатель никто не опирается.</p>
              ) : (
                <ul className={s.history}>
                  {impact.map((i) => (
                    <li key={i.linkId} style={{ paddingLeft: (i.depth - 1) * 16, display: 'flex', alignItems: 'center', gap: 8 }}>
                      <StatusDot tone={i.boundary ? 'unknown' : toneOf(i.status)} />
                      {i.boundary ? (
                        <span className="muted">
                          {i.nodeName}: {i.kpiTitle} — влияет на показатель смежного подразделения
                        </span>
                      ) : (
                        <KpiRef nodeId={i.nodeId} kpi={i.kpi} title={i.kpiTitle} nodeName={i.nodeName} />
                      )}
                      <span className="muted num">
                        вес {fmtNum(i.weight, 2)}
                        {i.depth > 1 ? ` · по пути ${fmtNum(i.product, 2)}` : ''}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              {impactTiles.size || impactStages.size ? (
                <div className={s.chips} style={{ marginTop: 8 }}>
                  {[...impactTiles].map((t) => (
                    <span key={t} className={s.chip}>
                      плитка «{tileName(t)}»
                    </span>
                  ))}
                  {[...impactStages].sort().map((st) => (
                    <Link key={st} className={s.chip} to={linkTo('/orders', { stage: st })}>
                      этап {st}
                    </Link>
                  ))}
                </div>
              ) : null}
              <p className={s.caption}>По весам связей структуры; это не прогноз эффекта.</p>
            </div>
            <div className={s.now}>
              <div className={s.nowLabel}>Затронуто заказов</div>
              <div className={s.affected}>{fmtNum(d.affected_orders?.count ?? 0, 0)}</div>
              <div className={s.chips} style={{ marginTop: 8 }}>
                {(d.affected_orders?.sample ?? []).filter((x) => x.startsWith('ORD-')).map((o) => (
                  <OrderRef key={o} id={o} />
                ))}
              </div>
              <p className={s.caption}>
                Заказы того же сегмента на этапе {d.affected_orders?.stage ?? d.context?.stage} в окне сигнала с проблемой (брак, просрочка или непройденная проверка). Цена отклонения — без денег.
              </p>
            </div>
          </div>
        </Section>

        {/* 3. Причина */}
        <CauseSection d={d} canManage={canManage} />

        {/* 4. Действие */}
        <ActionSection d={d} canManage={canManage} userName={userName} now={now} today={today} current={step === 3} />

        {/* 5. Проверка */}
        <Section id="check" n={5} title="Проверка" current={step === 4}>
          <CheckBody d={d} canRecheck={canRecheck} canDemo={canDemo} now={now} unit={unit} userName={userName} />
          {done && series.data ? (
            <div style={{ marginTop: 16 }}>
              <KpiChart
                points={series.data.points}
                unit={series.data.unit}
                thresholds={series.data.thresholds}
                now={now}
                from={dayStartIso(addDaysToKey(dayKey(done.baseline?.from ?? chartFrom), -2))}
                marks={chartMarks(series.data.flags, [d])}
                windows={recheckWindows(done, series.data.unit)}
                height={240}
              />
            </div>
          ) : null}
        </Section>

        {/* 6. История */}
        <section className={s.section} aria-labelledby="hist-h">
          <div className={s.sectionHead}>
            <h2 id="hist-h">История и журнал</h2>
            <span style={{ flex: 1 }} />
            <Link to={linkTo('/audit', { object_id: d.id })}>весь журнал по карточке</Link>
          </div>
          <div className={s.cols}>
            <ul className={s.history}>
              {(d.history ?? []).map((h, i) => (
                <li key={i}>
                  <time>{fmtDateTime(h.ts)}</time>
                  {userName(h.user)}: {historyText(h as Record<string, unknown>)}
                </li>
              ))}
            </ul>
            <ul className={s.history}>
              {(audit.data?.items ?? []).map((r) => (
                <li key={r.seq}>
                  <time>{fmtDateTime(r.ts)}</time>
                  {userName(r.user)} {auditAction(r.action, r.details as Record<string, unknown>)}
                  {r.details_hidden ? <span className="muted"> · детали скрыты: вне вашей зоны</span> : null}
                </li>
              ))}
            </ul>
          </div>
        </section>
      </div>
    </Page>
  );
}

function historyText(h: Record<string, unknown>): string {
  switch (h.change) {
    case 'created':
      return h.detected_by === 'auto' ? 'карточка создана автоматически' : 'карточка создана';
    case 'hypothesis':
      return 'записана гипотеза';
    case 'action':
      return 'назначено действие';
    case 'status':
      return `статус: ${DEVIATION_STATUS[h.from as keyof typeof DEVIATION_STATUS]?.label ?? h.from} → ${DEVIATION_STATUS[h.to as keyof typeof DEVIATION_STATUS]?.label ?? h.to}${h.comment ? ` («${h.comment}»)` : ''}`;
    case 'recheck':
      return `перепроверка № ${h.n}: ${h.result === 'pending' ? 'рано проверять' : h.result === 'passed' ? 'сработало' : 'не сработало'}`;
    case 'done':
      return 'действие отмечено выполненным';
    default:
      return String(h.change);
  }
}

/* ---------- 3. Причина ---------- */
function CauseSection({ d, canManage }: { d: Deviation; canManage: boolean }) {
  const linkTo = useLinkTo();
  const graph = useGraph();
  const patch = usePatchDeviation(d.id);
  const [hyp, setHyp] = useState(d.cause?.hypothesis ?? '');
  useEffect(() => setHyp(d.cause?.hypothesis ?? ''), [d.cause?.hypothesis]);
  const steps: TraceStep[] = d.cause?.trace ?? [];
  const root = d.cause?.root;
  const basis = d.cause?.confidence_basis;
  const basisNode = basis ? (graph.data?.nodes ?? []).find((n) => n.id === basis.node_id) : undefined;
  const basisKpi = basisNode?.kpis?.find((k) => k.name === basis?.kpi);
  const clickableIds = new Set((graph.data?.nodes ?? []).filter((n) => n.clickable).map((n) => n.id));
  return (
    <Section
      id="cause"
      n={3}
      title="Причина"
      current={false}
      extra={
        root ? (
          <Link className="btn btn-dark btn-sm" to={linkTo('/tree', { trace: `${d.node_id}:${d.kpi}`, dev: d.id, focus: root.node_id, panel: null, impact: null })}>
            <Crosshair size={16} aria-hidden />
            Открыть в дереве
          </Link>
        ) : null
      }
    >
      <div className={s.trace}>
        {steps.map((st, i) => (
          <div key={`${st.node_id}-${i}`} style={{ display: 'contents' }}>
            {i > 0 ? (
              <div className={s.traceArrow} aria-hidden>
                <span>{st.via?.share !== null && st.via?.share !== undefined ? fmtShare(st.via.share) : `вес ${fmtNum(st.via?.weight ?? 0, 2)}`}</span>
                <ArrowRight size={20} />
              </div>
            ) : null}
            <div className={`${s.traceNode} ${i === steps.length - 1 && steps.length > 1 ? s.traceRoot : ''} ${!st.visible ? s.traceHidden : ''}`}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <StatusDot tone={toneOf(st.status)} />
                <b>
                  <NodeLink id={st.node_id} clickable={st.visible && clickableIds.has(st.node_id)} owner={st.owner}>
                    {st.node_name}
                  </NodeLink>
                </b>
              </span>
              {st.visible ? (
                <>
                  <span className="muted">
                    {st.kpi && clickableIds.has(st.node_id) ? (
                      <KpiLink nodeId={st.node_id} kpi={st.kpi}>
                        {st.title}
                      </KpiLink>
                    ) : (
                      st.title
                    )}
                  </span>
                  <span className="num" style={{ fontWeight: 700, fontSize: 20 }}>
                    {fmtValue(st.value, st.unit)}
                  </span>
                </>
              ) : (
                <span className="muted">
                  {st.owner} · данные вне вашей зоны
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
      {steps.some((st) => (st.alternatives ?? []).length) ? (
        <p className={s.caption} style={{ fontSize: 14 }}>
          Альтернативы:{' '}
          {steps
            .flatMap((st) => st.alternatives ?? [])
            .map((a, i) => (
              <span key={a.link_id}>
                {i > 0 ? '; ' : ''}
                <NodeLink id={a.to_node} clickable={a.visible && clickableIds.has(a.to_node)} owner={a.owner}>
                  {a.to_node_name}
                </NodeLink>
                {a.status === 'yellow' ? ' (внимание)' : ''}
                {a.share !== null && a.share !== undefined ? ` — ${fmtShare(a.share)}` : ''}
              </span>
            ))}
        </p>
      ) : null}
      <p className={s.verdict}>{traceVerdict(steps, d.cause?.stopped_reason ?? '')}</p>
      <div className={s.chips} style={{ marginTop: 8 }}>
        {root ? (
          <span className={s.chip}>
            Первопричина:&nbsp;
            {root.kpi && clickableIds.has(root.node_id) ? (
              <KpiLink nodeId={root.node_id} kpi={root.kpi}>
                {root.node_name}
              </KpiLink>
            ) : (
              <NodeLink id={root.node_id} clickable={clickableIds.has(root.node_id)}>
                {root.node_name}
              </NodeLink>
            )}
          </span>
        ) : null}
        <span className={s.chip}>
          Уверенность: {CONFIDENCE[d.cause?.confidence ?? ''] ?? d.cause?.confidence}
          {basis ? (
            <>
              {' — '}
              <KpiLink nodeId={basis.node_id} kpi={basis.kpi} clickable={clickableIds.has(basis.node_id)}>
                {basisKpi?.title ?? basis.kpi}
                {basisNode ? ` (${basisNode.name})` : ''}
              </KpiLink>
              : {fmtValue(basis.value, basisKpi?.unit ?? '%')}
            </>
          ) : null}
        </span>
      </div>
      <div className={s.sub}>Гипотеза</div>
      {canManage ? (
        <>
          <textarea className={s.textarea} value={hyp} onChange={(e) => setHyp(e.target.value)} placeholder="Что, по-вашему, произошло? Например: партия новой обложки с дефектом." />
          <div className={s.actions} style={{ marginTop: 8 }}>
            <button
              type="button"
              className="btn btn-outline btn-sm"
              disabled={patch.isPending || hyp === (d.cause?.hypothesis ?? '')}
              onClick={() => patch.mutate({ hypothesis: hyp }, { onSuccess: () => toast('Гипотеза сохранена и записана в журнал'), onError: (e) => toast((e as Error).message, 'crit') })}
            >
              Сохранить гипотезу
            </button>
          </div>
        </>
      ) : (
        <p>{d.cause?.hypothesis || <span className="muted">Гипотезы пока нет.</span>}</p>
      )}
    </Section>
  );
}

/* ---------- 4. Действие ---------- */
function ActionSection({
  d,
  canManage,
  userName,
  now,
  today,
  current,
}: {
  d: Deviation;
  canManage: boolean;
  userName: (l: string | null | undefined) => string;
  now: string;
  today: string;
  current: boolean;
}) {
  const me = useMe();
  const users = useUsers();
  const patch = usePatchDeviation(d.id);
  const doneM = useDone(d.id);
  const showForm = needsAction(d.status) && canManage;
  const suggest = useSuggest(d.id, showForm);
  const [picked, setPicked] = useState<string | null>(null);
  const [text, setText] = useState('');
  const [owner, setOwner] = useState('');
  const [due, setDue] = useState('');
  const [ref, setRef] = useState<string | null>(null);
  const [errors, setErrors] = useState<Set<string>>(new Set());
  const [closeOpen, setCloseOpen] = useState(false);
  const [comment, setComment] = useState('');
  const a = d.action;
  const isOwner = !!me.data && (a?.owner_login === me.data.login || (!!me.data.node && a?.owner_node === me.data.node.id));
  const allowed = TRANSITIONS[d.status as keyof typeof TRANSITIONS] ?? [];

  const apply = (sg: { id: string; action: string; owner_hint?: string | null; due_at: string }) => {
    setPicked(sg.id);
    setText(sg.action);
    const u = users.data?.find((x) => x.name === sg.owner_hint);
    setOwner(u?.login ?? '');
    setDue(dayKey(sg.due_at));
    setRef(sg.id);
    setErrors(new Set());
  };

  const assign = () => {
    const miss = new Set<string>();
    if (!text.trim()) miss.add('text');
    if (!owner) miss.add('owner');
    if (!due) miss.add('due');
    setErrors(miss);
    if (miss.size) return;
    const body: PatchBody = { status: 'assigned', action: { text: text.trim(), owner_login: owner, due_at: `${due}T09:00:00+03:00`, playbook_ref: ref } };
    patch.mutate(body, {
      onSuccess: async (dev) => {
        toast('Решение сохранено и записано в журнал', 'ok');
        const short = text.trim().split(/[;.,]/)[0].slice(0, 48);
        await placeDecisionFlags(dev, `Решение: ${short}`, now, today);
      },
      onError: (e) => {
        if (e instanceof ApiError) {
          const errs = new Set<string>();
          const missing = (e.details.missing as string[] | undefined) ?? [];
          for (const m of missing) errs.add(m.includes('owner') ? 'owner' : m.includes('due') ? 'due' : 'text');
          for (const er of (e.details.errors as Array<{ loc: string[] }> | undefined) ?? []) {
            const last = er.loc[er.loc.length - 1];
            errs.add(last === 'owner_login' ? 'owner' : last === 'due_at' ? 'due' : 'text');
          }
          setErrors(errs);
          const allowedT = e.details.allowed as string[] | undefined;
          toast(allowedT ? `${e.message}. Допустимо: ${allowedT.map((x) => DEVIATION_STATUS[x as keyof typeof DEVIATION_STATUS]?.label ?? x).join(', ')}` : e.message, 'crit');
        } else toast((e as Error).message, 'crit');
      },
    });
  };

  const move = (status: string, cmt?: string) =>
    patch.mutate(
      { status, comment: cmt },
      {
        onSuccess: () => toast(`Статус: ${DEVIATION_STATUS[status as keyof typeof DEVIATION_STATUS]?.label}. Записано в журнал`),
        onError: (e) => toast((e as Error).message, 'crit'),
      },
    );

  return (
    <Section id="action" n={4} title="Действие" current={current}>
      {a?.text ? (
        <div className={s.actionCard}>
          <div style={{ fontWeight: 600, fontSize: 16 }}>{a.text}</div>
          <dl className={s.facts}>
            <dt>Ответственный</dt>
            <dd>{a.owner_login ? userName(a.owner_login) : a.owner_node ? <NodeRef id={a.owner_node} name={`узел ${a.owner_node}`} /> : '—'}</dd>
            <dt>Срок</dt>
            <dd>
              {a.due_at ? fmtDateTime(a.due_at) : '—'}
              {d.overdue ? <b style={{ color: 'var(--crit-ink)' }}> · просрочено</b> : null}
            </dd>
            <dt>Назначил</dt>
            <dd>
              {userName(a.assigned_by)} · {a.assigned_at ? fmtDateTime(a.assigned_at) : '—'}
            </dd>
            {a.playbook_ref ? (
              <>
                <dt>Шаблон</dt>
                <dd>{a.playbook_ref}</dd>
              </>
            ) : null}
            {a.done_at ? (
              <>
                <dt>Выполнено</dt>
                <dd>
                  {userName(a.done_by)} · {fmtDateTime(a.done_at)}
                </dd>
              </>
            ) : null}
          </dl>
        </div>
      ) : !showForm ? (
        <p className="muted">Действие ещё не назначено{canManage ? '' : ': назначает руководитель с правом управлять решениями'}.</p>
      ) : null}

      {showForm ? (
        <>
          <p className="muted" style={{ margin: a?.text ? '16px 0 8px' : '0 0 8px' }}>
            Подсказка по шаблонам действий (playbook). Здесь подключается ИИ-ассистент.
          </p>
          <div className={s.suggests}>
            {suggest.isPending ? (
              <Skeleton height={120} />
            ) : (
              (suggest.data?.suggestions ?? []).map((sg) => (
                <div key={sg.id} className={`${s.suggest} ${picked === sg.id ? s.suggestOn : ''}`}>
                  <span className={s.suggestTitle}>{sg.title}</span>
                  <span>{sg.action}</span>
                  <span className={s.suggestMeta}>
                    {sg.owner_hint ? `Кому: ${sg.owner_hint} · ` : ''}срок {sg.due_days} {plural(sg.due_days, ['день', 'дня', 'дней'])} · перепроверка через {sg.recheck_window_days} дн.
                  </span>
                  <button type="button" className="btn btn-outline btn-sm" style={{ alignSelf: 'flex-start' }} onClick={() => apply(sg)}>
                    Применить
                  </button>
                </div>
              ))
            )}
          </div>
          <div className={s.form}>
            <div className={`${s.field} ${s.fieldWide} ${errors.has('text') ? s.fieldError : ''}`}>
              <label htmlFor="act-text">Что сделать</label>
              <textarea id="act-text" className={s.textarea} value={text} onChange={(e) => setText(e.target.value)} />
            </div>
            <div className={`${s.field} ${errors.has('owner') ? s.fieldError : ''}`}>
              <label htmlFor="act-owner">Ответственный</label>
              <select id="act-owner" value={owner} onChange={(e) => setOwner(e.target.value)}>
                <option value="">выберите…</option>
                {(users.data ?? []).map((u) => (
                  <option key={u.login} value={u.login}>
                    {u.name}
                  </option>
                ))}
              </select>
            </div>
            <div className={`${s.field} ${errors.has('due') ? s.fieldError : ''}`}>
              <label htmlFor="act-due">Срок (по Минску)</label>
              <input id="act-due" type="date" min={today} value={due} onChange={(e) => setDue(e.target.value)} />
            </div>
            <div className={s.field}>
              <label>Шаблон</label>
              <span className="muted" style={{ lineHeight: '40px' }}>
                {ref ?? 'без шаблона'}
              </span>
            </div>
          </div>
          <div className={s.actions}>
            <button type="button" className="btn btn-primary" disabled={patch.isPending} onClick={assign}>
              <ShieldAlert size={16} aria-hidden />
              Назначить действие
            </button>
            {errors.size ? <span style={{ color: 'var(--crit-ink)' }}>Заполните отмеченные поля</span> : null}
          </div>
        </>
      ) : null}

      <div className={s.actions}>
        {canManage && allowed.includes('in_progress') ? (
          <button type="button" className="btn btn-outline btn-sm" onClick={() => move('in_progress')}>
            Взять в работу
          </button>
        ) : null}
        {isOwner && can(me.data?.permissions, 'deviations.done') && allowed.includes('done') ? (
          <button
            type="button"
            className="btn btn-dark btn-sm"
            onClick={() => doneM.mutate(null, { onSuccess: () => toast('Действие отмечено выполненным'), onError: (e) => toast((e as Error).message, 'crit') })}
          >
            Отметить выполненным
          </button>
        ) : null}
        {canManage && allowed.includes('escalated') ? (
          <button type="button" className="btn btn-outline btn-sm" onClick={() => move('escalated')}>
            Эскалировать
          </button>
        ) : null}
        {canManage && allowed.includes('closed') ? (
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setCloseOpen(true)}>
            Закрыть
          </button>
        ) : null}
      </div>
      <ConfirmDialog
        open={closeOpen}
        title={`Закрыть ${d.id}?`}
        text="Закрытая карточка не перепроверяется. Комментарий попадёт в историю и журнал."
        confirmLabel="Закрыть карточку"
        danger
        onCancel={() => setCloseOpen(false)}
        onConfirm={() => {
          setCloseOpen(false);
          move('closed', comment || undefined);
        }}
      >
        <textarea className={s.textarea} value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Почему закрываем" />
      </ConfirmDialog>
    </Section>
  );
}

/* ---------- 5. Проверка ---------- */
function CheckBody({
  d,
  canRecheck,
  canDemo,
  now,
  unit,
  userName,
}: {
  d: Deviation;
  canRecheck: boolean;
  canDemo: boolean;
  now: string;
  unit: string | null;
  userName: (l: string | null | undefined) => string;
}) {
  const recheck = useRecheck(d.id);
  const advance = useAdvanceWithChanges();
  const list = d.rechecks ?? [];
  const last = list[list.length - 1];
  const done = lastCompleted(list);
  const ref = d.action?.assigned_at ?? d.signal.ts;
  const elapsed = Math.max(0, daysBetween(ref, now));
  const early = elapsed < MIN_RECHECK_DAYS;
  const open = d.status !== 'verified' && d.status !== 'closed';
  const showPending = last?.result === 'pending' && early;

  return (
    <>
      {open && canRecheck ? (
        <div className={s.actions} style={{ marginTop: 0 }}>
          <button
            type="button"
            className={`btn ${needsAction(d.status) ? 'btn-outline' : 'btn-primary'}`}
            disabled={recheck.isPending}
            onClick={() =>
              recheck.mutate(undefined, {
                onSuccess: (r) => {
                  const res = r.recheck.result;
                  toast(res === 'pending' ? 'Рано проверять — запись добавлена в историю перепроверок' : res === 'passed' ? 'Перепроверка: решение сработало' : 'Перепроверка: не сработало', res === 'failed' ? 'crit' : 'ok');
                },
                onError: (e) => toast((e as Error).message, 'crit'),
              })
            }
          >
            <RefreshCw size={16} aria-hidden />
            Перепроверить
          </button>
          {!early && d.action?.assigned_at ? <span className="muted">Прошло {fmtNum(elapsed, 0)} сут. с назначения — можно проверять.</span> : null}
        </div>
      ) : open ? (
        <p className="muted">Перепроверку запускает руководитель с правом «Запускать перепроверку».</p>
      ) : null}

      {showPending ? (
        <div className={s.pending}>
          <b>
            Рано проверять: прошло {fmtNum(Math.floor(elapsed), 0)} из {MIN_RECHECK_DAYS} суток
          </b>
          <div className={s.progress}>
            <div className={s.progressFill} style={{ width: `${Math.min(100, (elapsed / MIN_RECHECK_DAYS) * 100)}%` }} />
          </div>
          <div className="muted">Это не ошибка: эффект действия видно не раньше чем через {MIN_RECHECK_DAYS} суток после назначения.</div>
          {canDemo ? (
            <button
              type="button"
              className="btn btn-dark btn-sm"
              style={{ marginTop: 10 }}
              disabled={advance.isPending}
              onClick={() => advance.mutate(7, { onError: (e) => toast((e as Error).message, 'crit') })}
            >
              <FastForward size={16} aria-hidden />
              Перемотать демо-время на 7 дней
            </button>
          ) : null}
        </div>
      ) : null}

      {done ? (
        <div className={`${s.result} ${done.result === 'passed' ? s.resultOk : s.resultBad}`}>
          {done.result === 'passed' ? 'Решение сработало' : 'Решение не сработало'}: {fmtValue(done.baseline?.value, unit)} → {fmtValue(done.after?.value, unit)}
          {done.improvement !== null && done.improvement !== undefined ? `, тяжесть отклонения снизилась на ${fmtShare(done.improvement)}` : ''}
        </div>
      ) : null}
      {d.status === 'verified' && !done ? <DevRef id={d.id} label="Проверено" /> : null}

      {list.length ? (
        <table className={s.table}>
          <thead>
            <tr>
              <th>№</th>
              <th>Когда</th>
              <th>Кто</th>
              <th>Правило</th>
              <th>До</th>
              <th>После</th>
              <th>Улучшение</th>
              <th>Итог</th>
            </tr>
          </thead>
          <tbody>
            {[...list].reverse().map((r) => (
              <tr key={r.n}>
                <td className={s.num}>{r.n}</td>
                <td className={s.num}>{fmtDateTime(r.ts)}</td>
                <td>{userName(r.user)}</td>
                <td>{r.rule ? RULE[r.rule] ?? r.rule : `окно ${r.window_days} сут.`}</td>
                <td className={s.num}>{r.baseline ? `${fmtValue(r.baseline.value, unit)} (${fmtDay(r.baseline.from)}–${fmtDay(r.baseline.to)})` : '—'}</td>
                <td className={s.num}>{r.after ? `${fmtValue(r.after.value, unit)} (${fmtDay(r.after.from)}–${fmtDay(r.after.to)})` : '—'}</td>
                <td className={s.num}>{r.improvement !== null && r.improvement !== undefined ? fmtShare(r.improvement) : '—'}</td>
                <td>
                  {r.result === 'pending' ? (
                    <span className="muted">рано проверять ({fmtNum(r.elapsed_days ?? 0, 1)} из {r.min_days} сут.)</span>
                  ) : r.result === 'passed' ? (
                    <StatusBadge status="green" size="sm" label="сработало" />
                  ) : (
                    <StatusBadge status="red" size="sm" label="не сработало" />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted" style={{ marginTop: 12 }}>
          Перепроверок пока не было. Каждая перепроверка добавляется в список и не перезаписывает прежние.
        </p>
      )}
    </>
  );
}
