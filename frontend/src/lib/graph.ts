// Модель видимого графа для дерева и инспектора. Только индексы и видимость —
// статусы, вклад и trace считает сервер.
import { statusRank } from './status';

export interface GKpi {
  name: string;
  title: string;
  status: string;
  severity?: number | null;
  pinned?: boolean | null;
  value?: number | null;
  unit?: string | null;
}

export interface GNode {
  id: number;
  name: string;
  type: string;
  owner: string;
  status?: string | null;
  deep_status?: string | null;
  boundary?: string | null;
  clickable: boolean;
  scope_root?: boolean;
  tile?: string | null;
  stage?: number | null;
  kpis: GKpi[];
}

export interface GLink {
  id: string;
  from_node: number;
  from_kpi: string;
  to_node: number;
  to_kpi?: string | null;
  weight: number;
  access: string;
  note: string;
  boundary?: string | null;
  contribution?: number | null;
  share?: number | null;
}

export interface GraphLike {
  nodes: GNode[];
  links: GLink[];
  roots: number[];
}

export interface GraphIndex {
  byId: Map<number, GNode>;
  linkById: Map<string, GLink>;
  /** Дети по связям inherit (скелет иерархии для раскладки и сворачивания). */
  children: Map<number, number[]>;
  parents: Map<number, number[]>;
  out: Map<number, GLink[]>;
  in: Map<number, GLink[]>;
  roots: number[];
}

function push<K, V>(m: Map<K, V[]>, k: K, v: V) {
  const arr = m.get(k);
  if (arr) arr.push(v);
  else m.set(k, [v]);
}

export function indexGraph(g: GraphLike): GraphIndex {
  const byId = new Map(g.nodes.map((n) => [n.id, n]));
  const linkById = new Map(g.links.map((l) => [l.id, l]));
  const children = new Map<number, number[]>();
  const parents = new Map<number, number[]>();
  const out = new Map<number, GLink[]>();
  const inn = new Map<number, GLink[]>();
  for (const l of g.links) {
    if (!byId.has(l.from_node) || !byId.has(l.to_node)) continue;
    push(out, l.from_node, l);
    push(inn, l.to_node, l);
    if (l.access === 'inherit') {
      const ch = children.get(l.from_node) ?? [];
      if (!ch.includes(l.to_node)) push(children, l.from_node, l.to_node);
      const pa = parents.get(l.to_node) ?? [];
      if (!pa.includes(l.from_node)) push(parents, l.to_node, l.from_node);
    }
  }
  // Корни раскладки: узлы без родителя по inherit (зона + граничные сверху).
  const roots = g.nodes.filter((n) => !(parents.get(n.id)?.length)).map((n) => n.id);
  return { byId, linkById, children, parents, out, in: inn, roots };
}

/** Путь от корня до узла по inherit-родителям (первый родитель). */
export function pathToRoot(idx: GraphIndex, id: number): GNode[] {
  const path: GNode[] = [];
  const seen = new Set<number>();
  let cur: number | undefined = id;
  while (cur !== undefined && !seen.has(cur)) {
    seen.add(cur);
    const n = idx.byId.get(cur);
    if (!n) break;
    path.unshift(n);
    cur = idx.parents.get(cur)?.[0];
  }
  return path;
}

/** Вкладка по умолчанию: худший статус, при равенстве — pinned, затем порядок в узле. */
export function defaultKpi(n: Pick<GNode, 'kpis'>): string | null {
  if (!n.kpis.length) return null;
  let best = n.kpis[0];
  for (const k of n.kpis.slice(1)) {
    const d = statusRank(k.status) - statusRank(best.status);
    if (d > 0 || (d === 0 && k.pinned && !best.pinned)) best = k;
  }
  return best.name;
}

/** Короткий код свёрнутой вкладки: первые буквы двух значимых слов («Доля брака» → «ДБ»). */
export function abbrev(title: string): string {
  const words = title
    .replace(/[«»"()]/g, ' ')
    .split(/[\s→/-]+/)
    .filter((w) => w.length > 1 || /\d/.test(w));
  const letters = words.slice(0, 2).map((w) => w[0]?.toUpperCase() ?? '');
  return letters.join('') || title.slice(0, 2);
}

function descendants(idx: GraphIndex, id: number, acc = new Set<number>()): Set<number> {
  for (const c of idx.children.get(id) ?? []) {
    if (acc.has(c)) continue;
    acc.add(c);
    descendants(idx, c, acc);
  }
  return acc;
}

function ancestors(idx: GraphIndex, id: number, acc = new Set<number>()): Set<number> {
  for (const p of idx.parents.get(id) ?? []) {
    if (acc.has(p)) continue;
    acc.add(p);
    ancestors(idx, p, acc);
  }
  return acc;
}

export interface VisibilityOpts {
  onlyProblems: boolean;
  /** Узлы, раскрытые кнопкой «+N узлов в норме». */
  opened: Set<number>;
  /** Узлы со свёрнутым поддеревом (шеврон). */
  collapsed: Set<number>;
  /** Всегда видимые (фокус, путь расследования). */
  pinned: number[];
}

export interface Visibility {
  visible: Set<number>;
  /** Сколько узлов поддерева скрыто под узлом (для «+N узлов»). */
  hidden: Map<number, number>;
}

export function computeVisibility(g: GraphLike, idx: GraphIndex, o: VisibilityOpts): Visibility {
  const all = g.nodes.map((n) => n.id);
  let visible: Set<number>;
  if (!o.onlyProblems) {
    visible = new Set(all);
  } else {
    visible = new Set<number>();
    const problem = (n: GNode) =>
      n.deep_status === 'red' || n.deep_status === 'yellow' || n.status === 'red' || n.status === 'yellow';
    for (const id of g.roots) visible.add(id);
    for (const n of g.nodes) {
      if (problem(n)) {
        visible.add(n.id);
        ancestors(idx, n.id).forEach((a) => visible.add(a));
      }
    }
    // Граничные узлы показываем, если связаны с видимым узлом зоны.
    for (const n of g.nodes) {
      if (!n.boundary) continue;
      const linked = [...(idx.out.get(n.id) ?? []), ...(idx.in.get(n.id) ?? [])].some(
        (l) => visible.has(l.from_node === n.id ? l.to_node : l.from_node),
      );
      if (linked) visible.add(n.id);
    }
  }
  for (const id of o.opened) {
    if (!visible.has(id)) continue;
    for (const c of idx.children.get(id) ?? []) visible.add(c);
  }
  for (const id of o.pinned) {
    visible.add(id);
    ancestors(idx, id).forEach((a) => visible.add(a));
  }
  for (const id of o.collapsed) {
    if (!visible.has(id)) continue;
    descendants(idx, id).forEach((d) => {
      if (!o.pinned.includes(d)) visible.delete(d);
    });
  }
  // Скрытый узел засчитывается ближайшему видимому предку (по первому inherit-родителю).
  const hidden = new Map<number, number>();
  for (const n of g.nodes) {
    if (visible.has(n.id)) continue;
    let cur = idx.parents.get(n.id)?.[0];
    const seen = new Set<number>();
    while (cur !== undefined && !visible.has(cur) && !seen.has(cur)) {
      seen.add(cur);
      cur = idx.parents.get(cur)?.[0];
    }
    if (cur !== undefined && visible.has(cur)) hidden.set(cur, (hidden.get(cur) ?? 0) + 1);
  }
  return { visible, hidden };
}

/** Связи, выходящие из KPI узла (для «Зависит от:»). */
export function linksOfKpi(idx: GraphIndex, nodeId: number, kpi: string): GLink[] {
  return (idx.out.get(nodeId) ?? []).filter((l) => l.from_kpi === kpi);
}
