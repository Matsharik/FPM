// Содержимое инспектора в URL: panel=node:11 | kpi:11:defect_rate | link:L-0018 | order:ORD-000142 | event:E-000974

export type Panel =
  | { kind: 'node'; nodeId: number }
  | { kind: 'kpi'; nodeId: number; kpi: string }
  | { kind: 'link'; linkId: string }
  | { kind: 'order'; orderId: string }
  | { kind: 'event'; eventId: string };

export function parsePanel(raw: string | null | undefined): Panel | null {
  if (!raw) return null;
  const [kind, a, ...rest] = raw.split(':');
  if (!a) return null;
  switch (kind) {
    case 'node': {
      const id = Number(a);
      return Number.isInteger(id) ? { kind, nodeId: id } : null;
    }
    case 'kpi': {
      const id = Number(a);
      const kpi = rest.join(':');
      return Number.isInteger(id) && kpi ? { kind, nodeId: id, kpi } : null;
    }
    case 'link':
      return { kind, linkId: a };
    case 'order':
      return { kind, orderId: a };
    case 'event':
      return { kind, eventId: a };
    default:
      return null;
  }
}

export function formatPanel(p: Panel): string {
  switch (p.kind) {
    case 'node':
      return `node:${p.nodeId}`;
    case 'kpi':
      return `kpi:${p.nodeId}:${p.kpi}`;
    case 'link':
      return `link:${p.linkId}`;
    case 'order':
      return `order:${p.orderId}`;
    case 'event':
      return `event:${p.eventId}`;
  }
}
