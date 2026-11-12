// Инспектор узла и KPI (5.4) — «полная полезная сводка».
// GET /api/nodes/{id} пишет «открыл узел» в журнал, поэтому грузится только здесь, при открытии.
import { Crosshair, Network, ShieldAlert } from 'lucide-react';
import { Fragment, useMemo } from 'react';
import { Link } from 'react-router';
import { useAudit, useClock, useContributions, useDeviations, useGraph, useMe, useNodeDetail, useNodeKpis, usePeople } from '../api/hooks';
import type { Deviation } from '../api/types';
import { useLinkTo } from '../app/nav';
import { auditAction } from '../lib/audit';
import { countLabel, fmtNum, fmtShare, fmtWeight } from '../lib/format';
import { defaultKpi, indexGraph, pathToRoot, type GraphLike } from '../lib/graph';
import { impactUp } from '../lib/impact';
import { can } from '../lib/permissions';
import { statusRank } from '../lib/status';
import { fmtDateTime, fmtDay } from '../lib/time';
import { InspectorShell } from '../ui/Inspector';
import { DevRef, KpiLink, KpiRef, NodeRef } from '../ui/Refs';
import { ErrorState, OutOfZone, Skeleton } from '../ui/States';
import { DeviationStatusBadge, StatusBadge, StatusDot, toneOf } from '../ui/Status';
import { KpiBlock } from './KpiBlock';
import s from './inspector.module.css';

export const NODE_TYPE: Record<string, string> = {
  system: 'компания',
  subsystem: 'подсистема',
  function: 'функция',
  department: 'подразделение',
  team: 'команда',
  person: 'сотрудник',
  partner: 'партнёр',
  product_line: 'продуктовая линия',
};

export interface ShellChrome {
  onBack: () => void;
  onClose: () => void;
  onResize: (w: number) => void;
}

const isOpen = (d: Deviation) => d.status !== 'verified' && d.status !== 'closed';

export function NodePanel({ nodeId, kpi, chrome }: { nodeId: number; kpi: string | null; chrome: ShellChrome }) {
  const graph = useGraph();
  const clock = useClock();
  const me = useMe();
  const linkTo = useLinkTo();
  const idx = useMemo(() => (graph.data ? indexGraph(graph.data as unknown as GraphLike) : null), [graph.data]);
  const gnode = idx?.byId.get(nodeId);
  const inZone = !!gnode && gnode.clickable;
  const detail = useNodeDetail(inZone ? nodeId : null);
  const kpis = useNodeKpis(inZone ? nodeId : null);
  const devQ = useDeviations(inZone ? { node: nodeId } : {});
  const focusKpi = kpi ?? (gnode ? defaultKpi(gnode) : null);
  const contrib = useContributions(inZone ? nodeId : null, focusKpi);
  const hasPeopleBelow = useMemo(() => {
    if (!idx) return false;
    const seen = new Set<number>();
    const stack = [nodeId];
    while (stack.length) {
      const id = stack.pop()!;
      for (const l of idx.out.get(id) ?? []) {
        if (seen.has(l.to_node)) continue;
        seen.add(l.to_node);
        if (idx.byId.get(l.to_node)?.type === 'person') return true;
        stack.push(l.to_node);
      }
    }
    return false;
  }, [idx, nodeId]);
  const people = usePeople(nodeId, inZone && hasPeopleBelow && can(me.data?.permissions, 'people.read'));
  const history = useAudit({ node: nodeId, limit: 10 }, inZone);

  if (graph.isPending || !clock.data) {
    return (
      <InspectorShell title={<Skeleton width={200} height={24} />} {...chrome}>
        <Skeleton height={200} />
      </InspectorShell>
    );
  }
  if (!gnode) {
    return (
      <InspectorShell title="Узел не найден" {...chrome}>
        <ErrorState error={new Error('Узла нет в вашей структуре: возможно, его удалили или стенд сброшен.')} />
      </InspectorShell>
    );
  }
  if (!gnode.clickable) {
    return (
      <InspectorShell kicker="Вне вашей зоны" title={gnode.name} {...chrome}>
        <OutOfZone owner={gnode.owner} what={`Данные узла «${gnode.name}»`} />
      </InspectorShell>
    );
  }

  const now = clock.data.now;
  const today = clock.data.today;
  const path = idx ? pathToRoot(idx, nodeId) : [];
  const cards = kpis.data ?? [];
  const devs = (devQ.data?.items ?? []) as Deviation[];
  const openDevs = devs.filter(isOpen);
  const crit = cards.filter((k) => k.status === 'red').length;
  const warn = cards.filter((k) => k.status === 'yellow').length;
  const problemKpi = cards
    .filter((k) => k.status === 'red' || k.status === 'yellow')
    .sort((a, b) => statusRank(b.status) - statusRank(a.status))[0];
  const traceKpi = kpi && cards.find((k) => k.name === kpi && (k.status === 'red' || k.status === 'yellow')) ? kpi : problemKpi?.name;
  const mainDev = openDevs[0];
  const canManage = can(me.data?.permissions, 'deviations.manage');
  const impact = idx ? impactUp(idx, nodeId, kpi) : [];
  const ranked = [...cards].sort((a, b) => (b.severity ?? 0) - (a.severity ?? 0));

  const summary = [
    countLabel(cards.length, ['KPI', 'KPI', 'KPI']),
    crit ? `${crit} критично` : null,
    warn ? `${warn} внимание` : null,
    `открытых решений: ${openDevs.length}`,
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <InspectorShell
      {...chrome}
      kicker={
        <span className={s.path}>
          {path.slice(0, -1).map((p, i) => (
            <Fragment key={p.id}>
              {i > 0 ? <span aria-hidden>/</span> : null}
              {p.clickable ? <Link to={linkTo('/tree', { focus: p.id, panel: `node:${p.id}` })}>{p.name}</Link> : <span>{p.name}</span>}
            </Fragment>
          ))}
        </span>
      }
      title={
        <>
          {gnode.name}
          {kpi ? <span className="muted" style={{ fontWeight: 500 }}> · {cards.find((k) => k.name === kpi)?.title ?? kpi}</span> : null}
        </>
      }
      status={
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <StatusBadge status={gnode.status} size="sm" />
          <span className={s.meta}>
            {NODE_TYPE[detail.data?.type ?? gnode.type] ?? gnode.type} · владелец: {gnode.owner}
          </span>
        </div>
      }
      actions={
        <>
          {mainDev ? (
            <Link className="btn btn-primary btn-sm" to={linkTo(`/deviations/${mainDev.id}`)}>
              <ShieldAlert size={16} aria-hidden />
              Открыть карточку {mainDev.id}
            </Link>
          ) : null}
          {traceKpi ? (
            <Link className="btn btn-dark btn-sm" to={linkTo('/tree', { trace: `${nodeId}:${traceKpi}`, focus: nodeId, impact: null })}>
              <Crosshair size={16} aria-hidden />
              Найти причину
            </Link>
          ) : null}
          {focusKpi ? (
            <Link className="btn btn-outline btn-sm" to={linkTo('/tree', { impact: `${nodeId}:${focusKpi}`, focus: nodeId, trace: null })}>
              <Network size={16} aria-hidden />
              Показать влияние
            </Link>
          ) : null}
        </>
      }
    >
      <p className={s.summary}>{summary}</p>

      <section className={s.section} aria-label="Показатели">
        {kpis.isPending ? (
          <Skeleton height={140} />
        ) : kpis.isError ? (
          <ErrorState error={kpis.error} onRetry={() => kpis.refetch()} />
        ) : cards.length === 0 ? (
          <p className="muted">У узла нет показателей.</p>
        ) : (
          (kpi ? [...cards.filter((k) => k.name === kpi), ...cards.filter((k) => k.name !== kpi)] : cards).map((k) => (
            <KpiBlock key={k.name} nodeId={nodeId} card={k} open={k.name === kpi} idx={idx} devs={devs} now={now} today={today} canManage={canManage} />
          ))
        )}
      </section>

      <section className={s.section}>
        <div className={s.sectionTitle}>Влияет на</div>
        {impact.length === 0 ? (
          <p className="muted">Выше по структуре на {kpi ? 'этот показатель' : 'этот узел'} никто не опирается.</p>
        ) : (
          <ul className={s.list}>
            {impact.map((i) => (
              <li key={`${i.linkId}-${i.depth}`} className={`${s.listItem} ${i.boundary ? s.listItemMuted : ''}`} style={{ paddingLeft: (i.depth - 1) * 16 }}>
                <StatusDot tone={i.boundary ? 'unknown' : toneOf(i.status)} />
                <span className={s.grow}>
                  {i.boundary ? (
                    <>
                      {i.nodeName}: {i.kpiTitle} — влияет на показатель смежного подразделения
                    </>
                  ) : (
                    <KpiRef nodeId={i.nodeId} kpi={i.kpi} title={i.kpiTitle} nodeName={i.nodeName} />
                  )}
                </span>
                <span className={s.weight}>
                  вес {fmtWeight(i.weight)}
                  {i.depth > 1 ? ` · по пути ${fmtWeight(i.product)}` : ''}
                </span>
              </li>
            ))}
          </ul>
        )}
        <p className={s.caption}>По весам связей структуры; это не прогноз эффекта.</p>
      </section>

      {contrib.data && contrib.data.links.length ? (
        <section className={s.section}>
          <div className={s.sectionTitle}>Вклад подразделений в «{contrib.data.title}»</div>
          <ul className={s.list}>
            {[...contrib.data.links]
              .sort((a, b) => (b.share ?? -1) - (a.share ?? -1))
              .map((l) => (
                <li key={l.link_id} className={`${s.listItem} ${!l.visible ? s.listItemMuted : ''}`}>
                  <StatusDot tone={toneOf(l.status)} />
                  <span className={s.grow}>
                    <NodeRef id={l.to_node} name={l.to_node_name} clickable={l.visible && !!idx?.byId.get(l.to_node)?.clickable} owner={l.owner} />
                    {l.visible && l.share !== null && l.share !== undefined ? (
                      <div className={s.bar}>
                        <div className={s.barFill} style={{ width: `${Math.round(l.share * 100)}%` }} />
                      </div>
                    ) : null}
                  </span>
                  <span className={s.num}>{l.visible ? fmtShare(l.share) : 'скрыто'}</span>
                </li>
              ))}
          </ul>
          <p className={s.caption}>Вклад = вес связи × тяжесть отклонения цели; доля — от суммы видимых вкладов.</p>
        </section>
      ) : null}

      {people.data && people.data.people.length ? (
        <section className={s.section}>
          <div className={s.sectionTitle}>Люди ниже по структуре</div>
          <ul className={s.list}>
            {[...people.data.people]
              .sort((a, b) => statusRank(b.status) - statusRank(a.status))
              .map((p) => (
                <li key={p.id} className={s.listItem}>
                  <StatusDot tone={toneOf(p.status)} />
                  <span className={s.grow}>
                    <NodeRef id={p.id} name={p.name} />
                  </span>
                  <span className={s.weight}>
                    {p.kpis.map((k) => `${k.title.split(' ')[0]} ${fmtNum(k.value)}`).join(' · ')}
                  </span>
                </li>
              ))}
          </ul>
        </section>
      ) : null}

      {ranked.length > 1 ? (
        <section className={s.section}>
          <div className={s.sectionTitle}>KPI узла по тяжести</div>
          <ul className={s.list}>
            {ranked.map((k) => (
              <li key={k.name} className={s.listItem}>
                <StatusDot tone={toneOf(k.status)} />
                <span className={s.grow}>
                  <KpiLink nodeId={nodeId} kpi={k.name}>
                    {k.title}
                  </KpiLink>
                </span>
                <span className={s.weight}>тяжесть {fmtNum(k.severity ?? 0, 2)}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className={s.section}>
        <div className={s.sectionTitle}>Решения</div>
        {devs.length === 0 ? (
          <p className="muted">Карточек, где узел — сигнал или первопричина, нет.</p>
        ) : (
          <ul className={s.list}>
            {devs.map((d) => (
              <li key={d.id} className={s.listItem}>
                <DevRef id={d.id} />
                <span className={s.grow}>{d.title}</span>
                <DeviationStatusBadge status={d.status} size="sm" />
                {d.action?.due_at ? <span className={s.weight}>срок {fmtDay(d.action.due_at)}</span> : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className={s.section}>
        <div className={s.sectionTitle}>
          История
          <Link to={linkTo('/audit', { node: nodeId })} className={s.weight}>
            весь журнал
          </Link>
        </div>
        {history.data?.items.length ? (
          <ul className={`${s.list} ${s.history}`}>
            {history.data.items.map((r) => (
              <li key={r.seq}>
                <time>{fmtDateTime(r.ts)}</time>
                {r.user} {auditAction(r.action, r.details as Record<string, unknown>)}
                {r.object_id ? ` ${String(r.object_id)}` : ''}
                {r.details_hidden ? <span className="muted"> · детали скрыты: вне вашей зоны</span> : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">{history.isPending ? 'Загружаю…' : 'Записей пока нет.'}</p>
        )}
      </section>
    </InspectorShell>
  );
}
