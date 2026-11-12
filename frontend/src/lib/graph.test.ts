import { describe, expect, it } from 'vitest';
import graphDirector from '../fixtures/graph.director.json';
import graphProd from '../fixtures/graph.head_prod.json';
import { abbrev, computeVisibility, defaultKpi, indexGraph, pathToRoot, type GraphLike } from './graph';
import { impactUp } from './impact';

const gd = graphDirector as unknown as GraphLike;
const gp = graphProd as unknown as GraphLike;

describe('graph', () => {
  const idx = indexGraph(gd);
  it('путь от корня по inherit', () => {
    expect(pathToRoot(idx, 11).map((n) => n.name)).toEqual(['Фотопринт', 'Производство', 'Сборка']);
  });
  it('вкладка по умолчанию — худший KPI, при равенстве pinned', () => {
    expect(defaultKpi(idx.byId.get(5)!)).toBe('defect_tickets_share');
    expect(defaultKpi(idx.byId.get(10)!)).toBe('site_load');
  });
  it('короткий код вкладки', () => {
    expect(abbrev('Доля брака')).toBe('ДБ');
    expect(abbrev('Оплата → передача в ТК')).toBe('ОП');
  });
  it('«только проблемные» у директора: корень, красная и жёлтая ветки', () => {
    const v = computeVisibility(gd, idx, { onlyProblems: true, opened: new Set(), collapsed: new Set(), pinned: [] });
    const names = [...v.visible].map((id) => idx.byId.get(id)!.name).sort();
    // Печать, Финансы и Подбор — через связи их ветки упираются в красную Сборку и жёлтые Смены (deep_status).
    expect(names).toEqual(
      ['HR', 'Печать', 'Подбор и кадры', 'Поддержка', 'Производство', 'Работа с клиентами', 'Сборка', 'Смены', 'Финансы', 'Фотопринт'].sort(),
    );
    expect(v.hidden.get(9)).toBe(5); // ОТК, Склад и три контролёра под ОТК
    expect(v.hidden.get(11)).toBe(3); // три сборщика
  });
  it('раскрытие «+N» и фокус', () => {
    const v = computeVisibility(gd, idx, { onlyProblems: true, opened: new Set([9]), collapsed: new Set(), pinned: [17] });
    expect(v.visible.has(12)).toBe(true);
    expect(v.visible.has(17)).toBe(true);
  });
  it('у head_prod Поддержка — граничный узел сверху с одним KPI', () => {
    const ip = indexGraph(gp);
    const sup = ip.byId.get(5)!;
    expect(sup.boundary).toBe('upstream');
    expect(sup.kpis.map((k) => k.name)).toEqual(['defect_tickets_share']);
    const v = computeVisibility(gp, ip, { onlyProblems: false, opened: new Set(), collapsed: new Set(), pinned: [] });
    expect(v.visible.has(5)).toBe(true);
  });
});

describe('impact (7.3)', () => {
  it('Сборка/доля брака влияет вверх на Поддержку и Производство', () => {
    const idx = indexGraph(gd);
    const items = impactUp(idx, 11, 'defect_rate');
    const top = items.filter((i) => i.depth === 1).map((i) => [i.nodeName, i.kpi, i.weight]);
    expect(top).toEqual(
      expect.arrayContaining([
        ['Производство', 'on_time_24h_share', 0.3],
        ['Поддержка', 'defect_tickets_share', 0.6],
      ]),
    );
    const root = items.find((i) => i.nodeName === 'Фотопринт');
    expect(root?.depth).toBe(2);
    expect(root?.product).toBeCloseTo(0.3 * 0.45, 6);
  });
  it('связь с чужим to_kpi не учитывается', () => {
    const idx = indexGraph(gd);
    // Сборка/site_load: связь Поддержка→Сборка указывает to_kpi=defect_rate, поэтому её нет
    const items = impactUp(idx, 11, 'site_load');
    expect(items.some((i) => i.nodeName === 'Поддержка')).toBe(false);
    expect(items.some((i) => i.nodeName === 'Производство')).toBe(true);
  });
});
