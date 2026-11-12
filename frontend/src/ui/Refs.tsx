// Ссылочные чипы: одинаковый вид и поведение везде (раздел 6).
import { CircleAlert, FileText, Gauge, Lock, Package, Workflow } from 'lucide-react';
import { Link } from 'react-router';
import { useHereLink, useLinkTo } from '../app/nav';
import { Tooltip } from './Floating';
import s from './ui.module.css';

const stop = (e: React.MouseEvent) => e.stopPropagation();

/** Узел → Структура + инспектор узла. Граничный узел — без перехода, с тултипом. */
export function NodeRef({ id, name, clickable = true, owner }: { id: number; name: string; clickable?: boolean; owner?: string | null }) {
  const linkTo = useLinkTo();
  if (!clickable) {
    return (
      <Tooltip content={`Вне вашей зоны.${owner ? ` Владелец: ${owner}` : ''}`}>
        <span className={`${s.ref} ${s.refDisabled}`} tabIndex={0}>
          <Lock size={14} aria-hidden />
          <span className={s.refText}>{name}</span>
        </span>
      </Tooltip>
    );
  }
  return (
    <Link className={s.ref} to={linkTo('/tree', { focus: id, panel: `node:${id}` })} onClick={stop}>
      <Workflow size={14} aria-hidden />
      <span className={s.refText}>{name}</span>
    </Link>
  );
}

/** KPI → Структура: узел в центре, вкладка раскрыта, инспектор на KPI. */
export function KpiRef({ nodeId, kpi, title, nodeName }: { nodeId: number; kpi: string; title: string; nodeName?: string | null }) {
  const linkTo = useLinkTo();
  return (
    <Link className={s.ref} to={linkTo('/tree', { focus: nodeId, kpi, panel: `kpi:${nodeId}:${kpi}` })} onClick={stop}>
      <Gauge size={14} aria-hidden />
      <span className={s.refText}>
        {nodeName ? `${nodeName}: ` : ''}
        {title}
      </span>
    </Link>
  );
}

/** Текстовая ссылка на KPI внутри фразы (тот же переход, что у KpiRef). Вне зоны — просто текст. */
export function KpiLink({ nodeId, kpi, children, clickable = true }: { nodeId: number; kpi: string; children: React.ReactNode; clickable?: boolean }) {
  const linkTo = useLinkTo();
  if (!clickable) return <>{children}</>;
  return (
    <Link className={s.inline} to={linkTo('/tree', { focus: nodeId, kpi, panel: `kpi:${nodeId}:${kpi}` })} onClick={stop}>
      {children}
    </Link>
  );
}

/** Текстовая ссылка на узел внутри фразы. Вне зоны — текст с тултипом. */
export function NodeLink({ id, children, clickable = true, owner }: { id: number; children: React.ReactNode; clickable?: boolean; owner?: string | null }) {
  const linkTo = useLinkTo();
  if (!clickable) {
    return (
      <Tooltip content={`Вне вашей зоны.${owner ? ` Владелец: ${owner}` : ''}`}>
        <span tabIndex={0}>{children}</span>
      </Tooltip>
    );
  }
  return (
    <Link className={s.inline} to={linkTo('/tree', { focus: id, panel: `node:${id}` })} onClick={stop}>
      {children}
    </Link>
  );
}

/** Карточка отклонения. */
export function DevRef({ id, label }: { id: string; label?: string }) {
  const linkTo = useLinkTo();
  return (
    <Link className={`${s.ref} ${s.refDev}`} to={linkTo(`/deviations/${id}`)} onClick={stop}>
      <CircleAlert size={14} aria-hidden />
      <span className={s.refText}>{label ?? id}</span>
    </Link>
  );
}

/** Заказ → карточка заказа в инспекторе на текущем экране. */
export function OrderRef({ id }: { id: string }) {
  const here = useHereLink();
  return (
    <Link className={s.ref} to={here({ panel: `order:${id}` })} onClick={stop}>
      <Package size={14} aria-hidden />
      <span className={s.refText}>{id}</span>
    </Link>
  );
}

/** Событие → инспектор события. */
export function EventRef({ id, label }: { id: string; label?: string }) {
  const here = useHereLink();
  return (
    <Link className={s.ref} to={here({ panel: `event:${id}` })} onClick={stop}>
      <FileText size={14} aria-hidden />
      <span className={s.refText}>{label ?? id}</span>
    </Link>
  );
}
