// Структура — дерево KPI (5.3). Состояние в URL: focus, kpi, only, labels, impact, trace, mode, panel.
import '@xyflow/react/dist/style.css';
import { ReactFlow, ReactFlowProvider, useReactFlow, type Edge } from '@xyflow/react';
import { Crosshair, Info, Maximize, Minus, Network, Plus, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import { devKey } from '../../api/deviationHooks';
import { useDeviations, useGraph, useMe, useTraceQuery } from '../../api/hooks';
import type { Deviation, TraceStep } from '../../api/types';
import { useCurrentUser, useGo, useSetParams } from '../../app/nav';
import { can } from '../../lib/permissions';
import { TraceStrip } from './TraceStrip';
import { EyesOfRole } from '../../ui/EyesOfRole';
import { fmtShare, fmtWeight } from '../../lib/format';
import { computeVisibility, defaultKpi, indexGraph, type GraphLike } from '../../lib/graph';
import { impactUp } from '../../lib/impact';
import { Popover } from '../../ui/Floating';
import { Segmented } from '../../ui/Segmented';
import { EmptyState, ErrorState, Skeleton } from '../../ui/States';
import { layoutTree, nodeSize } from './layout';
import { OrgNode, type NodeRole, type OrgNodeT } from './OrgNode';
import { WeightEdge, type EdgeTone, type WeightEdgeT } from './WeightEdge';
import s from './tree.module.css';

const nodeTypes = { org: OrgNode };
const edgeTypes = { weight: WeightEdge };

function parseRef(v: string | null): { node: number; kpi: string } | null {
  if (!v) return null;
  const i = v.indexOf(':');
  const node = Number(v.slice(0, i));
  const kpi = v.slice(i + 1);
  return Number.isInteger(node) && kpi ? { node, kpi } : null;
}

function Legend() {
  return (
    <div className={s.legend}>
      <span className={s.legendLine} />
      <span>связь раскрытого KPI, на подписи — вес</span>
      <span className={s.legendLine} style={{ borderTopStyle: 'dashed', opacity: 0.4 }} />
      <span>связи свёрнутых KPI</span>
      <span className={s.legendLine} style={{ borderTopColor: 'var(--unknown)' }} />
      <span>связь с узлом вне вашей зоны (без доли вклада)</span>
      <span>⚡</span>
      <span>межфункциональная связь: доступ по ней не передаётся</span>
      <span className={s.legendLine} style={{ borderTopColor: 'var(--impact)', borderTopWidth: 3 }} />
      <span>«Показать влияние»: показатели выше по структуре</span>
      <span style={{ display: 'inline-block', width: 40, height: 22, background: 'var(--hatch)', border: '1px dashed var(--border-strong)', borderRadius: 6 }} />
      <span>узел вне вашей зоны</span>
      <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 5, background: 'var(--crit)', boxShadow: '0 0 0 2px #fff, 0 0 0 3px var(--crit)' }} />
      <span>внутри ветки есть проблема</span>
    </div>
  );
}

function TreeInner() {
  const [sp] = useSearchParams();
  const setParams = useSetParams();
  const go = useGo();
  const me = useMe();
  const graph = useGraph();
  const devQ = useDeviations();
  const rf = useReactFlow();
  const qc = useQueryClient();
  const user = useCurrentUser();

  const focus = sp.get('focus') ? Number(sp.get('focus')) : null;
  const kpiParam = sp.get('kpi');
  const labels = sp.get('labels') === 'share' ? 'share' : 'weights';
  const impact = parseRef(sp.get('impact'));
  const trace = parseRef(sp.get('trace'));
  const build = sp.get('mode') === 'build';
  const onlyParam = sp.get('only');
  const onlyProblems = onlyParam ? onlyParam === 'problems' : !!me.data?.sees_everything;

  const [opened, setOpened] = useState<Set<number>>(new Set());
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());
  const [expanded, setExpanded] = useState<Map<number, string>>(new Map());
  const [pos, setPos] = useState<Map<number, { x: number; y: number }> | null>(null);
  const internal = useRef(false);
  const fitted = useRef(false);

  const g = graph.data as unknown as GraphLike | undefined;
  const idx = useMemo(() => (g ? indexGraph(g) : null), [g]);

  const impactItems = useMemo(() => (idx && impact ? impactUp(idx, impact.node, impact.kpi) : []), [idx, impact?.node, impact?.kpi]); // eslint-disable-line react-hooks/exhaustive-deps
  const impactNodes = useMemo(() => new Set(impactItems.map((i) => i.nodeId)), [impactItems]);
  const impactLinks = useMemo(() => new Set(impactItems.map((i) => i.linkId)), [impactItems]);

  // Расследование: из карточки — сохранённый cause.trace (из кэша, без повторного открытия), иначе /api/analysis/trace.
  const devParam = sp.get('dev');
  const cachedDev = devParam ? qc.getQueryData<Deviation>(devKey(user, devParam)) : undefined;
  const traceQ = useTraceQuery(trace && !cachedDev ? trace : null);
  const traceSteps: TraceStep[] = cachedDev?.cause?.trace ?? traceQ.data?.steps ?? [];
  const traceStopped = cachedDev?.cause?.stopped_reason ?? traceQ.data?.stopped_reason ?? '';
  const traceInfo = useMemo(() => {
    const nodes = new Set<number>();
    const links = new Set<string>();
    const alts = new Set<string>();
    const altNodes = new Set<number>();
    const kpis = new Map<number, string>();
    if (!trace) return { nodes, links, alts, altNodes, kpis, root: null as number | null };
    for (const st of traceSteps) {
      nodes.add(st.node_id);
      if (st.kpi) kpis.set(st.node_id, st.kpi);
      if (st.chosen) links.add(st.chosen.link_id);
      for (const a of st.alternatives ?? []) {
        alts.add(a.link_id);
        altNodes.add(a.to_node);
      }
    }
    const root = traceSteps.length ? traceSteps[traceSteps.length - 1].node_id : null;
    return { nodes, links, alts, altNodes, kpis, root };
  }, [trace, traceSteps]);

  const pinned = useMemo(() => {
    const p: number[] = [];
    if (focus !== null) p.push(focus);
    if (impact) p.push(impact.node, ...impactNodes);
    if (trace) p.push(...traceInfo.nodes, ...traceInfo.altNodes);
    return p;
  }, [focus, impact, impactNodes, trace, traceInfo]);

  const vis = useMemo(
    () => (g && idx ? computeVisibility(g, idx, { onlyProblems, opened, collapsed, pinned }) : null),
    [g, idx, onlyProblems, opened, collapsed, pinned],
  );
  const visKey = vis ? [...vis.visible].sort((a, b) => a - b).join(',') : '';

  useEffect(() => {
    if (!idx || !vis) return;
    let alive = true;
    layoutTree(idx, vis.visible).then((p) => alive && setPos(p));
    return () => {
      alive = false;
    };
  }, [idx, visKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const expandedOf = useCallback(
    (id: number): string | null => {
      const n = idx?.byId.get(id);
      if (!n) return null;
      if (impact && impact.node === id) return impact.kpi;
      if (focus === id && kpiParam && n.kpis.some((k) => k.name === kpiParam)) return kpiParam;
      const tk = traceInfo.kpis.get(id);
      if (tk && n.kpis.some((k) => k.name === tk)) return tk;
      return expanded.get(id) ?? defaultKpi(n);
    },
    [idx, focus, kpiParam, expanded, impact, traceInfo],
  );

  const openDevs = useMemo(() => ((devQ.data?.items ?? []) as Deviation[]).filter((d) => d.status !== 'verified' && d.status !== 'closed'), [devQ.data]);

  const onSelect = useCallback(
    (id: number) => {
      internal.current = true;
      setParams({ focus: id, kpi: null, panel: `node:${id}` });
    },
    [setParams],
  );
  const onTab = useCallback(
    (id: number, kpi: string) => {
      internal.current = true;
      setExpanded((m) => new Map(m).set(id, kpi));
      setParams({ focus: id, kpi, panel: `kpi:${id}:${kpi}` });
    },
    [setParams],
  );
  const onToggle = useCallback((id: number) => {
    setCollapsed((c) => {
      const n = new Set(c);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  }, []);
  const onOpenHidden = useCallback((id: number) => {
    setCollapsed((c) => {
      const n = new Set(c);
      n.delete(id);
      return n;
    });
    setOpened((o) => new Set(o).add(id));
  }, []);
  const onDev = useCallback((id: string) => go(`/deviations/${id}`), [go]);

  const nodes: OrgNodeT[] = useMemo(() => {
    if (!idx || !vis || !pos) return [];
    return [...vis.visible]
      .filter((id) => pos.has(id))
      .map((id) => {
        const n = idx.byId.get(id)!;
        let role: NodeRole = 'none';
        if (impact) role = id === impact.node ? 'impact-source' : impactNodes.has(id) ? 'impact-hit' : 'dim';
        else if (trace && traceSteps.length)
          role = id === traceInfo.root ? 'root' : traceInfo.nodes.has(id) ? 'path' : traceInfo.altNodes.has(id) ? 'alt' : 'dim';
        return {
          id: String(id),
          type: 'org' as const,
          position: pos.get(id)!,
          ...nodeSize(n),
          draggable: false,
          selectable: false,
          data: {
            node: n,
            expandedKpi: expandedOf(id),
            selected: focus === id,
            role,
            hidden: vis.hidden.get(id) ?? 0,
            collapsed: collapsed.has(id),
            hasChildren: (idx.children.get(id) ?? []).length > 0,
            devIds: openDevs.filter((d) => d.node_id === id).map((d) => d.id),
            pathKpis: trace && traceInfo.kpis.has(id) ? [traceInfo.kpis.get(id)!] : [],
            onSelect,
            onTab,
            onToggle,
            onOpenHidden,
            onDev,
          },
        };
      });
  }, [idx, vis, pos, impact, impactNodes, expandedOf, focus, collapsed, openDevs, onSelect, onTab, onToggle, onOpenHidden, onDev, trace, traceSteps, traceInfo]);

  const traceShares = useMemo(() => {
    const m = new Map<string, number | null | undefined>();
    for (const st of traceSteps) {
      if (st.chosen) m.set(st.chosen.link_id, st.chosen.share);
      for (const a of st.alternatives ?? []) m.set(a.link_id, a.share);
    }
    return m;
  }, [traceSteps]);

  const edges: WeightEdgeT[] = useMemo(() => {
    if (!g || !idx || !vis) return [];
    const out: WeightEdgeT[] = [];
    for (const l of g.links) {
      if (!vis.visible.has(l.from_node) || !vis.visible.has(l.to_node)) continue;
      const from = idx.byId.get(l.from_node)!;
      const to = idx.byId.get(l.to_node)!;
      const fk = from.kpis.find((k) => k.name === l.from_kpi);
      if (!fk) continue;
      let tone: EdgeTone;
      const tracing = !!trace && traceSteps.length > 0;
      if (impact) tone = impactLinks.has(l.id) ? 'impact' : 'dim';
      else if (tracing) tone = traceInfo.links.has(l.id) ? 'path' : traceInfo.alts.has(l.id) ? 'alt' : 'dim';
      else if (l.boundary) tone = 'boundary';
      else tone = expandedOf(l.from_node) === l.from_kpi ? 'active' : 'muted';
      const cross = l.access === 'none';
      const traceShare = tracing ? traceShares.get(l.id) : undefined;
      const label =
        traceShare !== undefined && traceShare !== null
          ? fmtShare(traceShare)
          : labels === 'share' && !l.boundary
            ? l.share === null || l.share === undefined
              ? null
              : fmtShare(l.share)
            : fmtWeight(l.weight);
      const tip = [
        `${fk.title} (${from.name}) зависит от узла «${to.name}» на ${fmtShare(l.weight)}.`,
        l.share !== null && l.share !== undefined ? `Вклад в отклонение: ${fmtShare(l.share)}.` : l.boundary ? 'Узел вне вашей зоны: вклад не показывается.' : '',
        l.note,
        cross ? 'Причинная связь между функциями: доступ по ней не передаётся.' : '',
      ]
        .filter(Boolean)
        .join(' ');
      out.push({
        id: l.id,
        type: 'weight',
        source: String(l.from_node),
        target: String(l.to_node),
        sourceHandle: `k:${l.from_kpi}`,
        targetHandle: 'in',
        zIndex: 0,
        data: { tone, label, cross, tooltip: tip, onOpen: () => setParams({ panel: `link:${l.id}` }) },
      } satisfies Edge as WeightEdgeT);
    }
    return out;
  }, [g, idx, vis, impact, impactLinks, expandedOf, labels, setParams, trace, traceSteps, traceInfo, traceShares]);

  // Первое появление — вписать всё; внешний фокус (KpiRef, «Как предотвратить») — центрировать узел.
  useEffect(() => {
    if (!pos || !nodes.length) return;
    if (!fitted.current) {
      fitted.current = true;
      requestAnimationFrame(() => {
        if (focus !== null && pos.has(focus)) {
          const n = idx!.byId.get(focus)!;
          const p = pos.get(focus)!;
          const sz = nodeSize(n);
          rf.setCenter(p.x + sz.width / 2, p.y + sz.height / 2 + 80, { zoom: 0.9, duration: 0 });
        } else rf.fitView({ padding: 0.12, maxZoom: 1 });
      });
      return;
    }
  }, [pos, nodes.length]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (internal.current) {
      internal.current = false;
      return;
    }
    if (focus === null || !pos?.has(focus) || !idx || !fitted.current) return;
    const n = idx.byId.get(focus)!;
    const p = pos.get(focus)!;
    const sz = nodeSize(n);
    rf.setCenter(p.x + sz.width / 2, p.y + sz.height, { zoom: Math.max(rf.getZoom(), 0.85), duration: 300 });
  }, [focus, pos]); // eslint-disable-line react-hooks/exhaustive-deps

  if (graph.isError) return <div style={{ padding: 32 }}><ErrorState error={graph.error} onRetry={() => graph.refetch()} /></div>;

  const focusNode = focus !== null ? idx?.byId.get(focus) : undefined;
  const focusKpi = focus !== null ? expandedOf(focus) : null;
  const focusKpiStatus = focusNode?.kpis.find((k) => k.name === focusKpi)?.status;
  const canTrace = !!focusNode?.clickable && (focusKpiStatus === 'red' || focusKpiStatus === 'yellow');
  const traceDevId =
    devParam ??
    (trace ? openDevs.find((d) => d.node_id === trace.node && d.kpi === trace.kpi)?.id ?? openDevs.find((d) => d.cause?.trace?.some((st) => st.node_id === trace.node && st.kpi === trace.kpi))?.id ?? null : null);
  const sourceName = impact ? idx?.byId.get(impact.node)?.name : null;
  const sourceKpi = impact ? idx?.byId.get(impact.node)?.kpis.find((k) => k.name === impact.kpi)?.title : null;

  return (
    <div className={s.screen}>
      <div className={s.toolbar}>
        <div className={s.title}>
          <h1>{build ? 'Конструктор' : 'Структура'}</h1>
        </div>
        <div className={s.tools}>
          <button type="button" className={s.toolBtn} onClick={() => rf.fitView({ padding: 0.12, maxZoom: 1, duration: 300 })} aria-label="Вписать в экран" title="Вписать в экран">
            <Maximize size={16} />
          </button>
          <button type="button" className={s.toolBtn} onClick={() => rf.zoomOut({ duration: 200 })} aria-label="Уменьшить">
            <Minus size={16} />
          </button>
          <button type="button" className={s.toolBtn} onClick={() => rf.zoomIn({ duration: 200 })} aria-label="Увеличить">
            <Plus size={16} />
          </button>
        </div>
        <div className={s.tools}>
          <button
            type="button"
            className={`${s.toolBtn} ${onlyProblems ? s.toolBtnOn : ''}`}
            aria-pressed={onlyProblems}
            onClick={() => {
              setOpened(new Set());
              setParams({ only: onlyProblems ? 'all' : 'problems' }, { replace: true });
            }}
          >
            Только проблемные
          </button>
          <Segmented
            label="Подписи связей"
            value={labels}
            options={[
              { value: 'weights', label: 'Веса' },
              { value: 'share', label: 'Вклад' },
            ]}
            onChange={(v) => setParams({ labels: v === 'share' ? 'share' : null }, { replace: true })}
          />
        </div>
        <div className={s.tools}>
          <button
            type="button"
            className={s.toolBtn}
            disabled={!canTrace}
            title={canTrace ? 'Путь от сигнала к первопричине' : 'Выберите KPI со статусом «Критично» или «Внимание»'}
            onClick={() => focus !== null && focusKpi && setParams({ trace: `${focus}:${focusKpi}`, impact: null })}
          >
            <Crosshair size={16} />
            Найти причину
          </button>
          <button
            type="button"
            className={`${s.toolBtn} ${impact ? s.toolBtnOn : ''}`}
            disabled={!focusNode?.clickable || !focusKpi}
            title={focusNode ? 'Какие показатели выше по структуре опираются на выбранный KPI' : 'Выберите узел'}
            onClick={() => (impact ? setParams({ impact: null }) : focus !== null && focusKpi && setParams({ impact: `${focus}:${focusKpi}`, trace: null }))}
          >
            <Network size={16} />
            Показать влияние
          </button>
          <Popover
            placement="bottom-end"
            trigger={
              <button type="button" className={s.toolBtn}>
                <Info size={16} />
                Легенда
              </button>
            }
          >
            <Legend />
          </Popover>
        </div>
        <div className={s.tools} style={{ padding: "4px 8px" }}>
          <EyesOfRole compact />
        </div>
        {impact ? (
          <div className={`${s.modeBanner} ${s.modeImpact}`}>
            <Network size={16} aria-hidden />
            <span>
              Влияние «{sourceKpi}» ({sourceName}): затронуто показателей выше по структуре — {impactItems.length}. По весам связей; это не прогноз эффекта.
            </span>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setParams({ impact: null })} aria-label="Выйти из режима влияния">
              <X size={16} />
            </button>
          </div>
        ) : null}
        {build ? (
          <div className={s.modeBanner}>
            <span>Режим конструктора: инструменты появятся в Ф6. Пока — обычная структура.</span>
          </div>
        ) : null}
      </div>
      <div className={s.flow} style={{ position: 'relative' }}>
        {trace && !impact && traceSteps.length ? (
          <TraceStrip
            steps={traceSteps}
            stopped={traceStopped}
            devId={traceDevId}
            start={trace}
            fromCard={!!devParam}
            canCreate={can(me.data?.permissions, 'deviations.manage')}
            onClose={() => setParams({ trace: null, dev: null })}
            onStep={(nodeId, kpi, visible) => {
              if (!visible) return;
              internal.current = true;
              setParams(kpi ? { focus: nodeId, kpi, panel: `kpi:${nodeId}:${kpi}` } : { focus: nodeId, panel: `node:${nodeId}` });
            }}
          />
        ) : null}
        {trace && traceQ.isError ? (
          <div style={{ position: 'absolute', left: 16, bottom: 16, zIndex: 6, width: 480 }}>
            <ErrorState error={traceQ.error} onRetry={() => traceQ.refetch()} />
          </div>
        ) : null}
        {!g || !pos ? (
          <div className={s.loading}>
            <Skeleton width={480} height={240} radius={16} />
          </div>
        ) : g.nodes.length === 0 ? (
          <div style={{ padding: 96 }}>
            <EmptyState title="В вашей зоне нет узлов" text="Структуру собирает методолог в конструкторе." />
          </div>
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable={false}
            minZoom={0.2}
            maxZoom={1.6}
            // Без обработчиков клика React Flow отключает приём кликов узлами и связями (pointer-events: none).
            // Сам выбор узла и вкладки обрабатывает OrgNode; здесь — только связи.
            onNodeClick={() => undefined}
            onEdgeClick={(_, e) => setParams({ panel: `link:${e.id}` })}
            proOptions={{ hideAttribution: false }}
          />
        )}
      </div>
    </div>
  );
}

export function TreeScreen() {
  return (
    <ReactFlowProvider>
      <TreeInner />
    </ReactFlowProvider>
  );
}
