// Инспектор связи и события.
import { useMemo } from 'react';
import { useGraph } from '../api/hooks';
import type { components } from '../api/schema';
import { useCurrentUser } from '../app/nav';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { fmtShare, fmtWeight } from '../lib/format';
import { indexGraph, type GraphLike } from '../lib/graph';
import { fmtDateTime } from '../lib/time';
import { InspectorShell } from '../ui/Inspector';
import { KpiRef, NodeRef, OrderRef } from '../ui/Refs';
import { ErrorState, Skeleton } from '../ui/States';
import type { ShellChrome } from './NodePanel';
import s from './inspector.module.css';

export const ACCESS_TEXT: Record<string, string> = {
  inherit: 'Передаёт доступ: руководитель узла-источника видит узел-цель',
  none: 'Только причинная связь между функциями: доступ по ней не передаётся',
};

export function LinkPanel({ linkId, chrome }: { linkId: string; chrome: ShellChrome }) {
  const graph = useGraph();
  const idx = useMemo(() => (graph.data ? indexGraph(graph.data as unknown as GraphLike) : null), [graph.data]);
  const l = idx?.linkById.get(linkId);
  if (!idx) {
    return (
      <InspectorShell title={<Skeleton width={200} height={24} />} {...chrome}>
        <Skeleton height={120} />
      </InspectorShell>
    );
  }
  if (!l) {
    return (
      <InspectorShell title={linkId} {...chrome}>
        <ErrorState error={new Error('Связи нет в вашей структуре.')} />
      </InspectorShell>
    );
  }
  const from = idx.byId.get(l.from_node);
  const to = idx.byId.get(l.to_node);
  const fromK = from?.kpis.find((k) => k.name === l.from_kpi);
  const toK = l.to_kpi ? to?.kpis.find((k) => k.name === l.to_kpi) : null;
  return (
    <InspectorShell kicker={`Связь ${l.id}`} title={`${from?.name ?? l.from_node} → ${to?.name ?? l.to_node}`} {...chrome}>
      <dl className={s.dl}>
        <dt>Откуда</dt>
        <dd>
          {from?.clickable ? <KpiRef nodeId={l.from_node} kpi={l.from_kpi} title={fromK?.title ?? l.from_kpi} nodeName={from.name} /> : <NodeRef id={l.from_node} name={from?.name ?? '?'} clickable={false} owner={from?.owner} />}
        </dd>
        <dt>Куда</dt>
        <dd>
          {to?.clickable && toK ? (
            <KpiRef nodeId={l.to_node} kpi={toK.name} title={toK.title} nodeName={to.name} />
          ) : (
            <NodeRef id={l.to_node} name={to?.name ?? '?'} clickable={!!to?.clickable} owner={to?.owner} />
          )}
        </dd>
        <dt>Вес</dt>
        <dd className="num">{fmtWeight(l.weight)}</dd>
        <dt>Доступ</dt>
        <dd>{ACCESS_TEXT[l.access] ?? l.access}</dd>
        {l.note ? (
          <>
            <dt>Примечание</dt>
            <dd>{l.note}</dd>
          </>
        ) : null}
        <dt>Вклад</dt>
        <dd>{l.contribution === null || l.contribution === undefined ? 'не показывается (вне вашей зоны)' : fmtWeight(l.contribution)}</dd>
        <dt>Доля вклада</dt>
        <dd>{l.share === null || l.share === undefined ? '—' : fmtShare(l.share)}</dd>
      </dl>
      <p className={s.caption}>Вклад = вес связи × тяжесть отклонения цели.</p>
    </InspectorShell>
  );
}

type EventOut = components['schemas']['EventOut'];

export function EventPanel({ eventId, chrome }: { eventId: string; chrome: ShellChrome }) {
  const user = useCurrentUser();
  const q = useQuery({
    queryKey: [user, 'event', eventId],
    queryFn: () => api<EventOut>(`/api/events/${eventId}`, { as: user ?? undefined }),
  });
  const e = q.data;
  const payload = (e?.payload ?? {}) as Record<string, unknown>;
  const targets = (payload.targets as Array<{ node_id: number; node: string; kpi: string }> | undefined) ?? [];
  const dims = (payload.dims as Record<string, string> | undefined) ?? {};
  const label = typeof payload.label === 'string' ? payload.label : e?.type;
  return (
    <InspectorShell kicker={`Событие ${eventId}`} title={label ?? eventId} {...chrome}>
      {q.isError ? (
        <ErrorState error={q.error} />
      ) : !e ? (
        <Skeleton height={120} />
      ) : (
        <>
          <dl className={s.dl}>
            <dt>Когда</dt>
            <dd>{fmtDateTime(e.ts)}</dd>
            <dt>Источник</dt>
            <dd>{e.source}</dd>
            <dt>Тип</dt>
            <dd>{e.type}</dd>
            {e.order_id ? (
              <>
                <dt>Заказ</dt>
                <dd>
                  <OrderRef id={e.order_id} />
                </dd>
              </>
            ) : null}
            {Object.entries(dims).map(([k, v]) => (
              <span key={k} style={{ display: 'contents' }}>
                <dt>{k === 'product_line' ? 'Линейка' : k === 'brand' ? 'Бренд' : k}</dt>
                <dd>{v}</dd>
              </span>
            ))}
            {Object.entries(payload)
              .filter(([k, v]) => !['label', 'targets', 'dims'].includes(k) && (typeof v === 'string' || typeof v === 'number'))
              .map(([k, v]) => (
                <span key={k} style={{ display: 'contents' }}>
                  <dt>{k}</dt>
                  <dd>{String(v)}</dd>
                </span>
              ))}
          </dl>
          {targets.length ? (
            <div style={{ marginTop: 16 }}>
              <div className={s.sectionTitle}>Затронутые показатели</div>
              <div className={s.chips}>
                {targets.map((t) => (
                  <KpiRef key={`${t.node_id}-${t.kpi}`} nodeId={t.node_id} kpi={t.kpi} title={t.kpi} nodeName={t.node} />
                ))}
              </div>
            </div>
          ) : null}
        </>
      )}
    </InspectorShell>
  );
}
