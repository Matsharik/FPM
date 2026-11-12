// KPI-карточка инспектора: свёрнутая (значение, статус, спарклайн) и раскрытая
// (график с таймфреймами, порогами, отметками, прогнозом, паспортом данных, «Зависит от»).
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router';
import { api } from '../api/client';
import { useContributions, useForecast, useGlossary, useSeries, useSources } from '../api/hooks';
import type { Deviation, Flag, KpiCard } from '../api/types';
import { useLinkTo, useSetParams } from '../app/nav';
import { fmtShare, fmtWeight } from '../lib/format';
import { type GraphIndex, linksOfKpi } from '../lib/graph';
import { KPI_STATUS, asKpiStatus } from '../lib/status';
import { addDaysToKey, dayStartIso } from '../lib/time';
import { GlossaryHint } from '../ui/GlossaryHint';
import { KpiChart, forecastPhrase, marksFromFlags, type ChartMark } from '../ui/KpiChart';
import { Provenance } from '../ui/Provenance';
import { DevRef, NodeRef } from '../ui/Refs';
import { Segmented } from '../ui/Segmented';
import { Sparkline } from '../ui/Sparkline';
import { Skeleton } from '../ui/States';
import { StatusBadge, toneOf } from '../ui/Status';
import { toast } from '../ui/Toast';
import { KpiValue } from '../ui/Values';
import s from './inspector.module.css';

const TF = [
  { value: '7', label: '7 дн.' },
  { value: '30', label: '30 дн.' },
  { value: '90', label: '90 дн.' },
  { value: '365', label: 'год' },
];
const FC = [
  { value: '0', label: 'без прогноза' },
  { value: '7', label: '7' },
  { value: '14', label: '14' },
  { value: '21', label: '21 дн.' },
];
const STRIPE: Record<string, string> = { ok: 'var(--ok)', warn: 'var(--warn)', crit: 'var(--crit)', unknown: 'var(--unknown)' };

function isOpenDev(d: Deviation) {
  return d.status !== 'verified' && d.status !== 'closed';
}

/** Карточки, где этот KPI — сигнал или первопричина. */
export function devsOfKpi(devs: Deviation[], nodeId: number, kpi: string): Deviation[] {
  return devs.filter(
    (d) => (d.node_id === nodeId && d.kpi === kpi) || (d.cause?.root?.node_id === nodeId && d.cause?.root?.kpi === kpi),
  );
}

/** Отметки графика: флажки ряда + сроки и назначения действий по карточкам. */
export function chartMarks(flags: Flag[] | undefined, devs: Deviation[]): ChartMark[] {
  const marks = marksFromFlags(flags);
  for (const d of devs) {
    const a = d.action;
    if (a?.assigned_at && !marks.some((m) => m.kind === 'decision' && m.ref === d.id)) {
      marks.push({ ts: a.assigned_at, kind: 'decision', label: 'Решение', ref: d.id });
    }
    if (a?.due_at) marks.push({ ts: a.due_at, kind: 'due', label: 'срок', ref: d.id });
  }
  return marks;
}

export function KpiBlock({
  nodeId,
  card,
  open,
  idx,
  devs,
  now,
  today,
  canManage,
}: {
  nodeId: number;
  card: KpiCard;
  open: boolean;
  idx: GraphIndex | null;
  devs: Deviation[];
  now: string;
  today: string;
  canManage: boolean;
}) {
  const [sp] = useSearchParams();
  const setParams = useSetParams();
  const navigate = useNavigate();
  const linkTo = useLinkTo();
  const sources = useSources();
  const glossary = useGlossary();
  const qc = useQueryClient();
  const tf = sp.get('tf') ?? '30';
  const fc = open ? sp.get('forecast') ?? '0' : '0';
  const sparkFrom = dayStartIso(addDaysToKey(today, -14));
  const chartFrom = dayStartIso(addDaysToKey(today, -Number(tf)));
  const series = useSeries({ nodeId, kpi: card.name, from: open ? chartFrom : sparkFrom, agg: 'day' });
  const forecast = useForecast(nodeId, card.name, open && fc !== '0' ? Number(fc) : null);
  const contrib = useContributions(open ? nodeId : null, open ? card.name : null);
  const tone = toneOf(card.status);
  const myDevs = devsOfKpi(devs, nodeId, card.name);
  const openDev = myDevs.find(isOpenDev);
  const metric = card.metric ? glossary.data?.metrics?.[card.metric] : undefined;

  const createCard = useMutation({
    mutationFn: () => api<Deviation>('/api/deviations', { method: 'POST', body: { node_id: nodeId, kpi: card.name, hypothesis: 'Превентивно: прогноз показывает пересечение порога' } }),
    onSuccess: (d) => {
      qc.invalidateQueries();
      toast(`Создана превентивная карточка ${d.id}`, 'ok');
      navigate(linkTo(`/deviations/${d.id}`));
    },
    onError: (e) => toast((e as Error).message, 'crit'),
  });

  const toggle = () =>
    setParams(open ? { panel: `node:${nodeId}`, kpi: null } : { panel: `kpi:${nodeId}:${card.name}`, kpi: card.name, focus: nodeId });

  const deps = idx ? linksOfKpi(idx, nodeId, card.name) : [];
  const atRisk = forecast.data?.enough_data && (forecast.data.crossings?.warn || forecast.data.crossings?.crit);

  return (
    <div className={`${s.kpi} ${open ? s.kpiOpen : ''}`}>
      <button type="button" className={s.kpiHead} onClick={toggle} aria-expanded={open}>
        <span className={s.kpiStripe} style={{ background: STRIPE[tone] }} aria-hidden />
        <span style={{ minWidth: 0 }}>
          <span className={s.kpiTitle}>
            {card.title}
            <span onClick={(e) => e.stopPropagation()}>
              <GlossaryHint metric={card.metric} />
            </span>
          </span>
          <span className={s.kpiSub}>
            <KpiValue value={card.value} unit={card.unit} size="sm" />
            <StatusBadge status={card.status} size="sm" />
            {card.stale ? <span className="muted">данные устарели</span> : null}
          </span>
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {!open ? (
            <span className={s.kpiSpark}>
              {series.data ? (
                <Sparkline points={series.data.points} unit={card.unit} warn={card.thresholds?.warn} direction={card.direction} height={32} tone={tone === 'crit' ? 'crit' : tone === 'warn' ? 'warn' : 'ink'} />
              ) : (
                <Skeleton height={32} />
              )}
            </span>
          ) : null}
          {open ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
        </span>
      </button>
      {open ? (
        <div className={s.kpiBody}>
          <div className={s.toolbar}>
            <Segmented label="Период" value={tf} options={TF} onChange={(v) => setParams({ tf: v === '30' ? null : v }, { replace: true })} />
            <Segmented label="Прогноз" value={fc} options={FC} onChange={(v) => setParams({ forecast: v === '0' ? null : v }, { replace: true })} />
          </div>
          {series.data ? (
            <KpiChart
              points={series.data.points}
              unit={series.data.unit}
              thresholds={series.data.thresholds}
              now={now}
              from={chartFrom}
              forecast={fc !== '0' ? forecast.data : null}
              marks={chartMarks(series.data.flags, myDevs)}
              currentStatusLabel={KPI_STATUS[asKpiStatus(series.data.status)].label}
              onMark={(m) => {
                if (m.kind === 'annotation' && m.ref) setParams({ panel: `event:${m.ref}` });
                else if (m.ref?.startsWith('DEV-')) navigate(linkTo(`/deviations/${m.ref}`));
              }}
            />
          ) : (
            <Skeleton height={260} />
          )}
          {series.data && series.data.points.length === 0 ? <p className="muted">За выбранный период точек нет.</p> : null}
          {fc !== '0' && forecast.data ? <div className={s.phrase}>{forecastPhrase(forecast.data)}</div> : null}
          {series.data ? (
            <Provenance
              now={now}
              sources={sources.data}
              data={{
                source: series.data.source,
                points: series.data.points.length,
                days: series.data.days,
                valueDate: series.data.value_date,
                stale: series.data.stale,
                agg: series.data.agg,
                profile: series.data.profile,
                definition: metric?.definition,
                formula: metric?.formula,
                owner: metric?.owner,
                extra:
                  fc !== '0' && forecast.data
                    ? [
                        ['Прогноз', forecast.data.method_text],
                        ['Окно', `${forecast.data.lookback_days} сут., история ${forecast.data.history_days} сут., σ = ${fmtWeight(forecast.data.sigma ?? null)}`],
                      ]
                    : [],
              }}
            />
          ) : null}

          {atRisk ? (
            <div className={s.improve}>
              <h4>Как улучшить перспективу</h4>
              {openDev ? (
                <div className={s.chips}>
                  По этому показателю уже есть карточка: <DevRef id={openDev.id} />
                </div>
              ) : canManage ? (
                <button type="button" className="btn btn-dark btn-sm" disabled={createCard.isPending} onClick={() => createCard.mutate()}>
                  Открыть превентивную карточку
                </button>
              ) : (
                <span className="muted">Назначить действие может руководитель с правом управлять решениями.</span>
              )}
              <p className={s.caption}>Ниже — какие подразделения тянут показатель (вклад по связям структуры).</p>
            </div>
          ) : null}

          {deps.length ? (
            <div style={{ marginTop: 12 }}>
              <div className={s.sectionTitle}>Зависит от</div>
              <div className={s.chips}>
                {deps.map((l) => {
                  const n = idx?.byId.get(l.to_node);
                  return (
                    <span key={l.id} className={s.depChip}>
                      <NodeRef id={l.to_node} name={n?.name ?? String(l.to_node)} clickable={n?.clickable ?? false} owner={n?.owner} />
                      <span className={s.weight}>
                        {fmtWeight(l.weight)}
                        {l.share !== null && l.share !== undefined ? ` · ${fmtShare(l.share)}` : ''}
                      </span>
                    </span>
                  );
                })}
              </div>
              {contrib.data?.summary ? <p className={s.caption}>Состав отклонения: {contrib.data.summary}</p> : null}
              {contrib.data && contrib.data.hidden_links > 0 ? (
                <p className={s.caption}>Связей вне вашей зоны: {contrib.data.hidden_links} — их вклад не показывается.</p>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
