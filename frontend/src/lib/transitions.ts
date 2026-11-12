// Таблица переходов статусов карточки — константа из контракта (FRONTEND_CONTRACT, раздел 5).
// verified и failed ставит только перепроверка.
import type { DeviationStatus } from '../api/types';

export const TRANSITIONS: Record<DeviationStatus, DeviationStatus[]> = {
  open: ['assigned', 'escalated', 'closed'],
  assigned: ['assigned', 'in_progress', 'done', 'escalated', 'closed'],
  in_progress: ['assigned', 'done', 'escalated', 'closed'],
  done: ['in_progress', 'closed'],
  failed: ['assigned', 'escalated', 'closed'],
  escalated: ['assigned', 'closed'],
  verified: ['closed'],
  closed: [],
};

export function canMove(from: string, to: DeviationStatus): boolean {
  return (TRANSITIONS[from as DeviationStatus] ?? []).includes(to);
}

/** Нужно ли новое действие (форма назначения). */
export function needsAction(status: string): boolean {
  return status === 'open' || status === 'escalated' || status === 'failed';
}

/** Текущий шаг цепочки Сигнал → Контекст → Причина → Действие → Проверка (0..4; 5 — пройдена). */
export function chainStep(status: string): number {
  if (status === 'verified' || status === 'closed') return 5;
  if (needsAction(status)) return 3;
  return 4;
}

export const MIN_RECHECK_DAYS = 3;
