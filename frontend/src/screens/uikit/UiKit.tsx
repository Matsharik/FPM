// #/ui — дизайн-система на реальных фикстурах (снимки ответов API после сброса).
// Фикстуры используются только здесь и в тестах, не как запасной источник данных.
import { useState } from 'react';
import type { KpiSeries, Tile as TileT } from '../../api/types';
import { Logo, PRODUCT_NAME, PRODUCT_SHORT } from '../../brand';
import overview from '../../fixtures/overview.director.json';
import overviewQc from '../../fixtures/overview.qc_otk.json';
import series11 from '../../fixtures/series.11.defect_rate.json';
import series5 from '../../fixtures/series.5.defect_tickets_share.json';
import clock from '../../fixtures/clock.json';
import { DEVIATION_STATUS, STAGE_STATUS } from '../../lib/status';
import { DemoClockView } from '../../shell/DemoClock';
import shell from '../../shell/shell.module.css';
import { Page } from '../../shell/Shell';
import { ChainStepper } from '../../ui/ChainStepper';
import { ConfirmDialog } from '../../ui/ConfirmDialog';
import { InspectorShell } from '../../ui/Inspector';
import { Provenance } from '../../ui/Provenance';
import { DevRef, EventRef, KpiRef, NodeRef, OrderRef } from '../../ui/Refs';
import { Segmented } from '../../ui/Segmented';
import { Sparkline } from '../../ui/Sparkline';
import { EmptyState, ErrorState, OutOfZone, Skeleton } from '../../ui/States';
import { DeviationStatusBadge, StageStatusBadge, StatusBadge } from '../../ui/Status';
import { Tile } from '../../ui/Tile';
import { toast } from '../../ui/Toast';
import { Delta, KpiValue } from '../../ui/Values';
import { ApiError } from '../../api/client';
import { ReactFlowProvider } from '@xyflow/react';
import type { Forecast } from '../../api/types';
import graphDirector from '../../fixtures/graph.director.json';
import graphProd from '../../fixtures/graph.head_prod.json';
import forecast5 from '../../fixtures/forecast.5.defect_tickets_share.json';
import { defaultKpi, type GNode, type GraphLike } from '../../lib/graph';
import { KpiChart, forecastPhrase, marksFromFlags } from '../../ui/KpiChart';
import { OrgNode } from '../tree/OrgNode';
import s from './uikit.module.css';

const gDir = graphDirector as unknown as GraphLike;
const gProd = graphProd as unknown as GraphLike;
const fc5 = forecast5 as unknown as Forecast;
const noop = () => undefined;

function OrgNodeView({ n, selected }: { n: GNode; selected: boolean }) {
  const props = {
    id: String(n.id),
    data: {
      node: n,
      expandedKpi: defaultKpi(n),
      selected,
      role: 'none' as const,
      hidden: n.id === 11 ? 3 : 0,
      collapsed: false,
      hasChildren: n.id === 11,
      devIds: n.id === 5 ? ['DEV-0001'] : [],
      pathKpis: [],
      onSelect: noop,
      onTab: noop,
      onToggle: noop,
      onOpenHidden: noop,
      onDev: noop,
    },
  } as unknown as Parameters<typeof OrgNode>[0];
  return <OrgNode {...props} />;
}

const tiles = overview.tiles as unknown as TileT[];
const qcTiles = overviewQc.tiles as unknown as TileT[];
const s11 = series11 as unknown as KpiSeries;
const s5 = series5 as unknown as KpiSeries;
const SOURCES = [
  { key: 'erp', title: 'ERP / производство', system: 'ERP', mode: 'mock', read_only: true, connector: 'в проде — коннектор только на чтение' },
];

const SWATCHES: Array<[string, string]> = [
  ['--bg', 'фон'],
  ['--surface', 'карточки'],
  ['--ink', 'кнопки, обводка'],
  ['--text', 'текст'],
  ['--text-muted', 'вторичный текст'],
  ['--border', 'рамки'],
  ['--accent', 'главное действие'],
  ['--ok', 'норма'],
  ['--warn', 'внимание'],
  ['--crit', 'критично'],
  ['--unknown', 'нет данных'],
  ['--impact', 'влияние вверх'],
];

function Section({ title, children, note }: { title: string; children: React.ReactNode; note?: string }) {
  return (
    <section className={s.section}>
      <h2>{title}</h2>
      {note ? <p className={s.note}>{note}</p> : null}
      <div className={s.row}>{children}</div>
    </section>
  );
}

export function UiKit() {
  const [units, setUnits] = useState<'natural' | 'relative'>('natural');
  const [dialog, setDialog] = useState(false);
  const quality = tiles.find((t) => t.key === 'quality')!;
  const team = tiles.find((t) => t.key === 'team')!;
  const clients = tiles.find((t) => t.key === 'clients')!;
  const empty = qcTiles.find((t) => t.kpis === 0)!;
  return (
    <Page>
      <div className={s.head}>
        <Logo size={48} />
        <div>
          <h1>
            {PRODUCT_NAME} · дизайн-система
          </h1>
          <p className={s.note}>
            Токены — <code>src/styles/tokens.css</code>, сокращение — {PRODUCT_SHORT}. Все примеры собраны из настоящих ответов API после сброса стенда.
          </p>
        </div>
      </div>

      <Section title="Цвет = смысл" note="Жёлтый — только главное действие и выбранный элемент; «Внимание» — оранжевый.">
        {SWATCHES.map(([v, label]) => (
          <div key={v} className={s.swatch}>
            <span className={s.chip} style={{ background: `var(${v})` }} />
            <code>{v}</code>
            <span className={s.note}>{label}</span>
          </div>
        ))}
      </Section>

      <Section title="Типографика" note="Inter, шкала 12 / 14 / 16 / 20 / 28 / 40 / 56, цифры табличные.">
        <div className={s.typeStack}>
          {[56, 40, 28, 20, 16, 14, 12].map((px) => (
            <div key={px} style={{ fontSize: px, fontWeight: px >= 28 ? 600 : 400, letterSpacing: px >= 28 ? '-0.02em' : 0, lineHeight: 1.2 }}>
              {px}&nbsp;px · Доля брака 6,4&nbsp;%
            </div>
          ))}
        </div>
      </Section>

      <Section title="Кнопки" note="Одна жёлтая кнопка на экране — следующий шаг.">
        <button type="button" className="btn btn-primary">Открыть карточку DEV-0001</button>
        <button type="button" className="btn btn-dark">Назначить</button>
        <button type="button" className="btn btn-outline">Как предотвратить</button>
        <button type="button" className="btn btn-ghost">Отмена</button>
        <button type="button" className="btn btn-outline" disabled>Недоступно</button>
      </Section>

      <Section title="Статусы KPI и плиток">
        {(['green', 'yellow', 'red', 'unknown'] as const).map((st) => (
          <StatusBadge key={st} status={st} />
        ))}
        {(['green', 'yellow', 'red', 'unknown'] as const).map((st) => (
          <StatusBadge key={`sm-${st}`} status={st} size="sm" />
        ))}
      </Section>
      <Section title="Статусы решений">
        {Object.keys(DEVIATION_STATUS).map((st) => (
          <DeviationStatusBadge key={st} status={st} />
        ))}
      </Section>
      <Section title="Статусы этапов заказа">
        {Object.keys(STAGE_STATUS).map((st) => (
          <StageStatusBadge key={st} status={st} />
        ))}
      </Section>

      <Section title="Значения и дельта" note="Единица — из поля unit ответа.">
        <KpiValue value={quality.main_kpi?.value} unit={quality.main_kpi?.unit} size="xl" />
        <KpiValue value={s11.value} unit={s11.unit} size="lg" />
        <KpiValue value={team.main_kpi?.value} unit={team.main_kpi?.unit} size="md" />
        <Delta value={quality.main_kpi?.delta_week} unit={quality.main_kpi?.unit} trend={quality.main_kpi?.trend} quality={quality.main_kpi?.trend_quality} status="red" note="за 7 дн." />
        <Delta value={team.main_kpi?.delta_week} unit={team.main_kpi?.unit} trend={team.main_kpi?.trend} quality={team.main_kpi?.trend_quality} status="yellow" />
        <Delta value={-5.36} unit="%" trend="down" quality="improving" status="green" />
        <Segmented
          label="Единицы"
          value={units}
          onChange={setUnits}
          options={[
            { value: 'natural', label: 'Натуральные' },
            { value: 'relative', label: '% к цели' },
          ]}
        />
      </Section>

      <Section title="Спарклайн и паспорт данных" note="Линия факта — цвет текста, бледная зона — хуже порога «внимание».">
        <div className={s.box}>
          <div className={s.note}>Сборка · Доля брака, 14 дн.</div>
          <Sparkline points={s11.points} unit={s11.unit} warn={s11.thresholds?.warn} direction={s11.direction} tone="crit" />
          <Provenance now={clock.now} sources={SOURCES} data={{ source: s11.source, points: s11.points.length, days: s11.days, valueDate: s11.value_date, stale: s11.stale, agg: s11.agg, profile: s11.profile }} />
        </div>
        <div className={s.box}>
          <div className={s.note}>Поддержка · Доля обращений по браку</div>
          <Sparkline points={s5.points} unit={s5.unit} warn={s5.thresholds?.warn} direction={s5.direction} tone="crit" />
          <Provenance compact now={clock.now} sources={SOURCES} data={{ source: s5.source, valueDate: s5.value_date, stale: s5.stale }} />
        </div>
      </Section>

      <Section title="Ссылочные чипы" note="Одинаковый вид и поведение на всех экранах.">
        <NodeRef id={11} name="Сборка" />
        <NodeRef id={11} name="Сборка" clickable={false} owner="Зам. по производству" />
        <KpiRef nodeId={11} kpi="defect_rate" title="Доля брака" nodeName="Сборка" />
        <DevRef id="DEV-0001" />
        <OrderRef id="ORD-000142" />
        <EventRef id="E-000974" label="Запуск новой обложки" />
      </Section>

      <Section title="Плитки Пульса">
        <div className={s.tiles}>
          <Tile tile={quality} series={s5} action={<span className="btn btn-primary btn-sm">Открыть карточку DEV-0001</span>} />
          <Tile tile={team} seriesLoading />
          <Tile tile={clients} />
          <Tile tile={empty} />
        </div>
      </Section>

      <Section title="Цепочка решения">
        <div style={{ width: '100%' }}>
          <ChainStepper current={3} />
        </div>
      </Section>

      <Section title="Демо-время и инспектор">
        <div className={shell.clock}>
          <DemoClockView now={clock.now} interactive />
        </div>
        <div className={s.inspectorDemo}>
          <InspectorShell kicker="Узел · подразделение" title="Сборка" status={<StatusBadge status="red" />} onBack={() => undefined} onClose={() => undefined}>
            <p className={s.note}>2 KPI · 1 критично · открытых решений: 1</p>
          </InspectorShell>
        </div>
      </Section>

      <Section title="Пустые и ошибочные состояния" note="Без слова «ошибка», с объяснением причины.">
        <div className={s.states}>
          <EmptyState title="Задач нет" text="Ваши показатели в норме." />
          <OutOfZone owner="Зам. по производству" what="Цифры «Сборки»" />
          <ErrorState error={new ApiError(404, 'deviation_not_found', "карточка 'DEV-9999' не найдена")} />
          <div style={{ display: 'grid', gap: 8, alignContent: 'start' }}>
            <Skeleton height={24} width="60%" />
            <Skeleton height={44} />
            <Skeleton height={16} width="40%" />
          </div>
        </div>
      </Section>

      <Section title="Тост и подтверждение">
        <button type="button" className="btn btn-outline" onClick={() => toast('Решение сохранено и записано в журнал')}>
          Показать тост
        </button>
        <button type="button" className="btn btn-outline" onClick={() => setDialog(true)}>
          Показать подтверждение
        </button>
        <ConfirmDialog
          open={dialog}
          title="Сбросить стенд?"
          text="Удалятся решения, отметки и правки конструктора; стенд вернётся к исходному состоянию."
          confirmLabel="Сбросить стенд"
          danger
          onCancel={() => setDialog(false)}
          onConfirm={() => setDialog(false)}
        />
      </Section>
      <Section title="Узлы дерева и вкладки KPI" note="Вкладка — порт связи; полоса сверху — статус KPI. Выбранный узел — жёлтый «курсор».">
        <ReactFlowProvider>
          <div className={s.nodes}>
            {[
              { n: gDir.nodes.find((x) => x.id === 11)!, sel: true },
              { n: gDir.nodes.find((x) => x.id === 5)!, sel: false },
              { n: gProd.nodes.find((x) => x.id === 5)!, sel: false },
              { n: gProd.nodes.find((x) => x.id === 23)!, sel: false },
            ].map(({ n, sel }) => (
              <div key={`${n.id}-${n.boundary}`} className={s.nodeBox}>
                <OrgNodeView n={n} selected={sel} />
              </div>
            ))}
          </div>
        </ReactFlowProvider>
      </Section>

      <Section title="График KPI" note="Факт, пороги, «сейчас», прогноз с коридором ±1σ, отметки событий и сигнала.">
        <div className={s.box} style={{ width: 720 }}>
          <KpiChart
            points={s5.points}
            unit={s5.unit}
            thresholds={s5.thresholds}
            now={clock.now}
            from={s5.points[0]?.ts ?? clock.now}
            forecast={fc5}
            marks={marksFromFlags(s5.flags)}
          />
          <div className={s.note}>{forecastPhrase(fc5)}</div>
        </div>
      </Section>
    </Page>
  );
}
