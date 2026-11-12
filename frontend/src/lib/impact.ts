// «На что влияет» (7.3): цепочка ВВЕРХ по связям видимого графа.
// Связь a/k_a → b влияет на показатель a/k_a, если b — текущий узел и (to_kpi пуст или равен текущему KPI).
// Глубина до 4. Произведение весов — «по весам связей структуры; это не прогноз эффекта».
import type { GraphIndex } from './graph';

export interface ImpactItem {
  nodeId: number;
  nodeName: string;
  kpi: string;
  kpiTitle: string;
  status: string | null;
  depth: number;
  linkId: string;
  weight: number;
  /** Произведение весов по пути от исходного показателя. */
  product: number;
  /** Узел вне зоны (граничный). */
  boundary: boolean;
  owner: string;
}

export function impactUp(idx: GraphIndex, nodeId: number, kpi: string | null, maxDepth = 4): ImpactItem[] {
  const out: ImpactItem[] = [];
  const seen = new Set<string>([`${nodeId}:${kpi ?? '*'}`]);
  let frontier: Array<{ node: number; kpi: string | null; product: number }> = [{ node: nodeId, kpi, product: 1 }];
  for (let depth = 1; depth <= maxDepth && frontier.length; depth++) {
    const next: typeof frontier = [];
    for (const f of frontier) {
      for (const l of idx.in.get(f.node) ?? []) {
        if (l.to_kpi && f.kpi && l.to_kpi !== f.kpi) continue;
        const key = `${l.from_node}:${l.from_kpi}`;
        if (seen.has(key)) continue;
        seen.add(key);
        const n = idx.byId.get(l.from_node);
        if (!n) continue;
        const k = n.kpis.find((x) => x.name === l.from_kpi);
        const product = f.product * l.weight;
        out.push({
          nodeId: n.id,
          nodeName: n.name,
          kpi: l.from_kpi,
          kpiTitle: k?.title ?? l.from_kpi,
          status: k?.status ?? n.status ?? null,
          depth,
          linkId: l.id,
          weight: l.weight,
          product,
          boundary: !!n.boundary,
          owner: n.owner,
        });
        next.push({ node: n.id, kpi: l.from_kpi, product });
      }
    }
    frontier = next;
  }
  return out;
}
