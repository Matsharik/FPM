import { describe, expect, it } from 'vitest';
import overview from '../fixtures/overview.director.json';
import { diffOverview, readyForRecheck, type OverviewSnap } from './changes';
import { TRANSITIONS, canMove, chainStep } from './transitions';

const before = overview as unknown as OverviewSnap;

function clone(): OverviewSnap {
  return JSON.parse(JSON.stringify(before));
}

describe('что изменилось', () => {
  it('без изменений — пусто', () => {
    expect(diffOverview(before, clone())).toEqual([]);
  });
  it('смена статуса плитки и значение того же главного KPI', () => {
    const after = clone();
    const q = after.tiles.find((t) => t.key === 'quality')!;
    q.status = 'green';
    q.main_kpi!.value = 3.64;
    after.portfolio.verified = 1;
    after.portfolio.open = 0;
    const items = diffOverview(before, after);
    expect(items[0].text).toBe('Качество: Критично → Норма; Доля обращений по браку: 9 % → 3,64 %');
    expect(items[1].text).toBe('Решения: открыто 1 → 0, проверено 0 → 1');
  });
  it('значение другого главного KPI не сравнивается', () => {
    const after = clone();
    const t = after.tiles.find((x) => x.key === 'team')!;
    t.status = 'green';
    t.main_kpi = { ...t.main_kpi!, kpi: 'other', value: 1 };
    expect(diffOverview(before, after)[0].text).toBe('Команда · ресурс: Внимание → Норма');
  });
  it('готовы к перепроверке через 3 суток после назначения', () => {
    const devs = [
      { id: 'DEV-0001', title: 'x', node_name: 'y', status: 'assigned', action: { assigned_at: '2026-11-23T09:00:00+03:00' } },
      { id: 'DEV-0002', title: 'x', node_name: 'y', status: 'open', action: null },
    ];
    expect(readyForRecheck(devs, '2026-11-25T09:00:00+03:00', 3)).toEqual([]);
    expect(readyForRecheck(devs, '2026-11-30T09:00:00+03:00', 3).map((d) => d.id)).toEqual(['DEV-0001']);
  });
});

describe('переходы', () => {
  it('таблица из контракта', () => {
    expect(TRANSITIONS.open).toEqual(['assigned', 'escalated', 'closed']);
    expect(canMove('open', 'verified')).toBe(false);
    expect(canMove('verified', 'closed')).toBe(true);
    expect(chainStep('open')).toBe(3);
    expect(chainStep('assigned')).toBe(4);
    expect(chainStep('verified')).toBe(5);
  });
});
