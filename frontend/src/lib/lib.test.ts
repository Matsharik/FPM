import { describe, expect, it } from 'vitest';
import { NBSP, fmtDelta, fmtNum, fmtShare, fmtValue, fmtWeight, plural } from './format';
import { addDaysIso, addDaysToKey, dayKey, dayStartIso, fmtClock, fmtDay, relativeDay } from './time';
import { DEVIATION_STATUS, KPI_STATUS, trendTone, worstStatus } from './status';
import { levelLabel } from './permissions';
import { heaviestTileWithDeviation, priorityIndicators, pulseVerdict } from './pulse';
import { formatPanel, parsePanel } from './panel';
import overview from '../fixtures/overview.director.json';
import overviewQc from '../fixtures/overview.qc_otk.json';

describe('format', () => {
  it('десятичная запятая и неразрывный пробел перед единицей', () => {
    expect(fmtValue(9, '%')).toBe(`9${NBSP}%`);
    expect(fmtValue(6.4, '%')).toBe(`6,4${NBSP}%`);
    expect(fmtValue(3045, 'шт')).toBe(`3${NBSP}045${NBSP}шт`);
    expect(fmtValue(null, '%')).toBe('—');
    expect(fmtNum(99.03)).toBe('99,03');
    expect(fmtNum(320)).toBe('320');
  });
  it('вес и доля', () => {
    expect(fmtWeight(0.6)).toBe('0,6');
    expect(fmtWeight(0.25)).toBe('0,25');
    expect(fmtShare(0.923077)).toBe(`92${NBSP}%`);
  });
  it('дельта процентов — в процентных пунктах, со знаком', () => {
    expect(fmtDelta(3.5, '%')).toBe(`+3,5${NBSP}п.п.`);
    expect(fmtDelta(-2.98, 'индекс')).toBe(`−2,98${NBSP}индекс`);
    expect(fmtDelta(0, 'шт')).toBe(`0${NBSP}шт`);
  });
  it('склонение', () => {
    expect(plural(1, ['день', 'дня', 'дней'])).toBe('день');
    expect(plural(3, ['день', 'дня', 'дней'])).toBe('дня');
    expect(plural(11, ['день', 'дня', 'дней'])).toBe('дней');
    expect(plural(22, ['день', 'дня', 'дней'])).toBe('дня');
  });
});

describe('time (Europe/Minsk)', () => {
  it('точка ряда в 21:00Z — следующие сутки по Минску', () => {
    expect(dayKey('2026-11-21T21:00:00Z')).toBe('2026-11-22');
    expect(dayKey('2026-11-23T09:00:00+03:00')).toBe('2026-11-23');
    expect(dayKey('2026-11-23T00:30:00+03:00')).toBe('2026-11-23');
  });
  it('подписи даты и часов', () => {
    expect(fmtDay('2026-11-21T21:00:00Z')).toBe(`22${NBSP}нояб`);
    expect(fmtClock('2026-11-23T09:00:00+03:00')).toBe(`пн, 23${NBSP}нояб, 09:00`);
  });
  it('арифметика суток', () => {
    expect(addDaysToKey('2026-11-23', -14)).toBe('2026-11-09');
    expect(dayStartIso('2026-11-09')).toBe('2026-11-09T00:00:00+03:00');
    expect(addDaysIso('2026-11-23T09:00:00+03:00', 3)).toBe('2026-11-26T09:00:00+03:00');
    expect(relativeDay('2026-11-22', '2026-11-23T09:00:00+03:00')).toBe('вчера');
    expect(relativeDay('2026-11-20', '2026-11-23T09:00:00+03:00')).toBe(`3${NBSP}дн. назад`);
  });
});

describe('status', () => {
  it('переводы', () => {
    expect(KPI_STATUS.yellow.label).toBe('Внимание');
    expect(KPI_STATUS.yellow.tone).toBe('warn');
    expect(DEVIATION_STATUS.verified.label).toBe('Проверено: сработало');
  });
  it('худший статус игнорирует «нет данных»', () => {
    expect(worstStatus(['green', 'unknown', 'yellow'])).toBe('yellow');
    expect(worstStatus(['unknown', null])).toBe('unknown');
    expect(worstStatus(['green', 'red'])).toBe('red');
  });
  it('цвет дельты', () => {
    expect(trendTone('worsening', 'red')).toBe('crit');
    expect(trendTone('worsening', 'yellow')).toBe('warn');
    expect(trendTone('improving', 'green')).toBe('ok');
    expect(trendTone('stable', 'green')).toBe('unknown');
  });
  it('уровень управления', () => {
    expect(levelLabel('admin', true)).toBe('Руководство');
    expect(levelLabel('admin', false)).toBe('Руководитель функции');
    expect(levelLabel('qc')).toBe('Операционная команда');
  });
});

describe('pulse (на реальном ответе после сброса)', () => {
  it('вердикт директора', () => {
    const v = pulseVerdict(overview.tiles);
    expect(v.sentence).toBe('6 из 8 процессов в норме. Критично: Качество. Внимание: Команда.');
  });
  it('индикаторы приоритетов', () => {
    const ind = priorityIndicators(overview.tiles);
    expect(ind.map((i) => [i.priority, i.status])).toEqual([
      ['time', 'green'],
      ['quality', 'red'],
      ['cost', 'yellow'],
    ]);
  });
  it('у ОТК нет плиток «Срок» — индикатор не показывается', () => {
    const ind = priorityIndicators(overviewQc.tiles);
    expect(ind.map((i) => i.priority)).toEqual(['quality', 'cost']);
    expect(pulseVerdict(overviewQc.tiles).outOfZone).toBe(6);
  });
  it('жёлтая кнопка — на самой тяжёлой плитке с отклонением', () => {
    expect(heaviestTileWithDeviation(overview.tiles)?.key).toBe('quality');
  });
});

describe('panel', () => {
  it('разбор и сборка', () => {
    for (const raw of ['node:11', 'kpi:11:defect_rate', 'link:L-0018', 'order:ORD-000142', 'event:E-000974']) {
      const p = parsePanel(raw);
      expect(p).not.toBeNull();
      expect(formatPanel(p!)).toBe(raw);
    }
    expect(parsePanel('node:x')).toBeNull();
    expect(parsePanel('')).toBeNull();
  });
});
