// Действия журнала — человеческими словами (5.13).
export const AUDIT_ACTION: Record<string, string> = {
  'node.open': 'открыл узел',
  'deviation.open': 'открыл карточку',
  'deviation.create': 'создал карточку',
  'deviation.update': 'изменил карточку',
  'deviation.recheck': 'перепроверил',
  'deviation.done': 'отметил выполненным',
  'demo.advance': 'перемотал время',
  'demo.reset': 'сбросил стенд',
  'flag.add': 'поставил отметку',
  'flag.remove': 'убрал отметку',
  'points.add': 'внёс значения',
  'node.create': 'добавил узел',
  'node.update': 'изменил узел',
  'node.delete': 'удалил узел',
  'kpi.create': 'добавил KPI',
  'kpi.update': 'изменил KPI',
  'kpi.delete': 'удалил KPI',
  'link.create': 'добавил связь',
  'link.update': 'изменил связь',
  'link.delete': 'удалил связь',
  'weights.set': 'изменил веса',
  'glossary.create': 'добавил метрику',
  'glossary.update': 'изменил метрику',
  'config.export': 'выгрузил конфигурацию',
  'config.import': 'загрузил конфигурацию',
};

export function auditAction(action: string, details?: Record<string, unknown> | null): string {
  if (action === 'deviation.update' && details && typeof details.status === 'string') {
    if (details.status === 'assigned') return 'назначил действие';
    return 'сменил статус';
  }
  if (action === 'deviation.update' && details?.hypothesis === true) return 'записал гипотезу';
  return AUDIT_ACTION[action] ?? action;
}
