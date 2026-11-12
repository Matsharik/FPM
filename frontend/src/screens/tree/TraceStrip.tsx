// Пошаговая полоса расследования (5.5): шаги пути, пояснение остановки, D73, финальная кнопка.
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Crosshair, ShieldAlert, X } from 'lucide-react';
import { Link } from 'react-router';
import { api } from '../../api/client';
import type { Deviation, TraceStep } from '../../api/types';
import { useGo, useLinkTo } from '../../app/nav';
import { fmtShare, fmtValue } from '../../lib/format';
import { toast } from '../../ui/Toast';
import { StatusDot, toneOf } from '../../ui/Status';
import s from './trace.module.css';

export const STOPPED: Record<string, string> = {
  below_threshold: 'дальше вклад меньше 15 %, причина найдена здесь',
  out_of_zone: 'путь уходит в подразделение вне вашей зоны',
  no_links: 'у показателя нет связей ниже — причина найдена здесь',
  no_kpi: 'у узла-цели нет показателей — дальше идти некуда',
  max_depth: 'достигнута предельная глубина поиска',
};

/** Пояснение к результату trace с правилом D73: невидимый последний шаг — не «причина у вас». */
export function traceVerdict(steps: TraceStep[], stopped: string): string {
  const last = steps[steps.length - 1];
  if (!last) return '';
  if (!last.visible) {
    return `Причина в смежном подразделении: ${last.node_name} · ответственный ${last.owner}. Данные вне вашей зоны.`;
  }
  return `Первопричина: ${last.node_name} · ${last.title ?? ''} — ${STOPPED[stopped] ?? stopped}.`;
}

export function TraceStrip({
  steps,
  stopped,
  devId,
  start,
  canCreate,
  onStep,
  onClose,
  fromCard,
}: {
  steps: TraceStep[];
  stopped: string;
  devId: string | null;
  start: { node: number; kpi: string };
  canCreate: boolean;
  onStep: (nodeId: number, kpi: string | null, visible: boolean) => void;
  onClose: () => void;
  fromCard: boolean;
}) {
  const linkTo = useLinkTo();
  const go = useGo();
  const qc = useQueryClient();
  const create = useMutation({
    mutationFn: () => api<Deviation>('/api/deviations', { method: 'POST', body: { node_id: start.node, kpi: start.kpi } }),
    onSuccess: (d) => {
      qc.invalidateQueries();
      toast(`Создана карточка ${d.id}`, 'ok');
      go(`/deviations/${d.id}`);
    },
    onError: (e) => toast((e as Error).message, 'crit'),
  });
  return (
    <section className={s.strip} aria-label="Расследование">
      <div className={s.head}>
        <Crosshair size={18} aria-hidden />
        <b>Путь к первопричине</b>
        <span className={s.count}>
          шагов: {steps.length}
        </span>
        <span className={s.spacer} />
        {fromCard && devId ? (
          <Link className="btn btn-ghost btn-sm" to={linkTo(`/deviations/${devId}`)}>
            <ArrowLeft size={16} aria-hidden />
            Назад в карточку
          </Link>
        ) : null}
        <button type="button" className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Выйти из расследования">
          <X size={16} />
        </button>
      </div>
      <ol className={s.steps}>
        {steps.map((st, i) => {
          const next = st.chosen;
          return (
            <li key={`${st.node_id}-${i}`} className={s.step}>
              <button type="button" className={s.stepBtn} onClick={() => onStep(st.node_id, st.kpi ?? null, st.visible)}>
                <span className={s.stepNum}>Шаг {i + 1} из {steps.length}</span>
                <span className={s.stepMain}>
                  <StatusDot tone={toneOf(st.status)} />
                  <b>{st.node_name}</b>
                  {st.visible ? (
                    <>
                      {' · '}
                      {st.title} {fmtValue(st.value, st.unit)}
                    </>
                  ) : (
                    <span className={s.hidden}> · данные вне вашей зоны</span>
                  )}
                </span>
                {next ? (
                  <span className={s.stepNext}>
                    → главный вклад: {next.to_node_name}
                    {next.share !== null && next.share !== undefined ? ` (${fmtShare(next.share)})` : ''}
                    {(st.alternatives ?? []).length
                      ? `; альтернативы: ${(st.alternatives ?? [])
                          .map((a) => `${a.to_node_name}${a.share !== null && a.share !== undefined ? ` ${fmtShare(a.share)}` : ''}`)
                          .join(', ')}`
                      : ''}
                  </span>
                ) : (st.alternatives ?? []).length ? (
                  <span className={s.stepNext}>
                    альтернативы ниже порога:{' '}
                    {(st.alternatives ?? [])
                      .map((a) => `${a.to_node_name}${a.status === 'yellow' ? ' (внимание)' : ''}${a.share !== null && a.share !== undefined ? ` ${fmtShare(a.share)}` : ''}`)
                      .join(', ')}
                  </span>
                ) : null}
              </button>
            </li>
          );
        })}
      </ol>
      <div className={s.foot}>
        <p className={s.verdict}>{traceVerdict(steps, stopped)}</p>
        {devId ? (
          <Link className="btn btn-primary" to={linkTo(`/deviations/${devId}`)}>
            <ShieldAlert size={16} aria-hidden />
            Открыть карточку {devId}
          </Link>
        ) : canCreate ? (
          <button type="button" className="btn btn-primary" disabled={create.isPending} onClick={() => create.mutate()}>
            Создать карточку
          </button>
        ) : null}
      </div>
      <p className={s.formula}>Вклад = вес связи × тяжесть отклонения цели; путь идёт по наибольшему вкладу, пока он не ниже 15 %.</p>
    </section>
  );
}
