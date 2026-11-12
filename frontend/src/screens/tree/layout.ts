// Раскладка дерева: ELK layered сверху вниз, KPI-вкладки — порты с фиксированным порядком.
// Скелет — связи inherit; межфункциональные (none) участвуют, только если иначе узлу не на что опереться
// (граничный узел снизу у руководителя функции), — иначе дерево растягивается по слоям.
import ELK from 'elkjs/lib/elk.bundled.js';
import type { GraphIndex, GNode } from '../../lib/graph';

const elk = new ELK();

export const CARD_H = 84;
export const TABS_H = 44;
export const TAB_OPEN_W = 176;
export const TAB_W = 36;
export const TAB_GAP = 4;
const PAD_X = 12;

export function nodeSize(n: GNode): { width: number; height: number } {
  const k = n.kpis.length;
  const tabs = k ? PAD_X * 2 + TAB_OPEN_W + (k - 1) * (TAB_W + TAB_GAP) : 0;
  return { width: Math.max(236, tabs), height: CARD_H + (k ? TABS_H : 0) };
}

export async function layoutTree(idx: GraphIndex, visible: Set<number>): Promise<Map<number, { x: number; y: number }>> {
  const ids = [...visible].sort((a, b) => a - b);
  const children = ids.map((id) => {
    const n = idx.byId.get(id)!;
    const size = nodeSize(n);
    return {
      id: String(id),
      ...size,
      layoutOptions: { 'elk.portConstraints': 'FIXED_ORDER' },
      ports: [
        { id: `${id}:in`, layoutOptions: { 'elk.port.side': 'NORTH' } },
        ...n.kpis.map((k, i) => ({ id: `${id}:k:${k.name}`, layoutOptions: { 'elk.port.side': 'SOUTH', 'elk.port.index': String(n.kpis.length - i) } })),
      ],
    };
  });
  const edges: Array<{ id: string; sources: string[]; targets: string[] }> = [];
  for (const id of ids) {
    const inc = (idx.in.get(id) ?? []).filter((l) => visible.has(l.from_node));
    const inherit = inc.filter((l) => l.access === 'inherit');
    const use = inherit.length ? inherit : inc;
    for (const l of use) {
      edges.push({ id: l.id, sources: [`${l.from_node}:k:${l.from_kpi}`], targets: [`${id}:in`] });
    }
  }
  const res = await elk.layout({
    id: 'root',
    layoutOptions: {
      'elk.algorithm': 'layered',
      'elk.direction': 'DOWN',
      'elk.layered.spacing.nodeNodeBetweenLayers': '104',
      'elk.spacing.nodeNode': '36',
      'elk.layered.considerModelOrder.strategy': 'NODES_AND_EDGES',
      'elk.layered.nodePlacement.strategy': 'BRANDES_KOEPF',
      'elk.layered.crossingMinimization.forceNodeModelOrder': 'false',
    },
    children,
    edges,
  });
  const pos = new Map<number, { x: number; y: number }>();
  for (const c of res.children ?? []) pos.set(Number(c.id), { x: c.x ?? 0, y: c.y ?? 0 });
  return pos;
}
