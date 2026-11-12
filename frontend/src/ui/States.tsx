import { CircleSlash, Inbox, Lock, SearchX } from 'lucide-react';
import type { ReactNode } from 'react';
import { ApiError, NetworkError } from '../api/client';
import s from './ui.module.css';

export function EmptyState({ title, text, action, icon }: { title: string; text?: ReactNode; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className={s.state}>
      <span className={s.stateIcon}>{icon ?? <Inbox size={20} />}</span>
      <div className={s.stateTitle}>{title}</div>
      {text ? <div className={s.stateText}>{text}</div> : null}
      {action}
    </div>
  );
}

export function OutOfZone({ owner, what = 'Эти данные' }: { owner?: string | null; what?: string }) {
  return (
    <div className={`${s.state} ${s.stateOut}`}>
      <span className={s.stateIcon}>
        <Lock size={20} />
      </span>
      <div className={s.stateTitle}>Вне вашей зоны доступа</div>
      <div className={s.stateText}>
        {what} относятся к подразделению вне вашей зоны.{owner ? ` Ответственный: ${owner}.` : ''}
      </div>
    </div>
  );
}

/** Ошибка запроса: «не найдено», «вне зоны» или понятный текст сервера. */
export function ErrorState({ error, onRetry, back }: { error: unknown; onRetry?: () => void; back?: ReactNode }) {
  if (error instanceof ApiError && error.code === 'out_of_zone') return <OutOfZone />;
  const notFound = error instanceof ApiError && error.isNotFound;
  const title = notFound ? 'Не найдено' : error instanceof NetworkError ? 'Сервер не отвечает' : 'Не удалось загрузить';
  const text = error instanceof Error ? error.message : String(error);
  return (
    <div className={`${s.state} ${s.stateErr}`}>
      <span className={s.stateIcon}>{notFound ? <SearchX size={20} /> : <CircleSlash size={20} />}</span>
      <div className={s.stateTitle}>{title}</div>
      <div className={s.stateText}>{text}</div>
      <div style={{ display: 'flex', gap: 8 }}>
        {onRetry ? (
          <button type="button" className="btn btn-outline btn-sm" onClick={onRetry}>
            Повторить
          </button>
        ) : null}
        {back}
      </div>
    </div>
  );
}

export function Skeleton({ height = 16, width = '100%', radius }: { height?: number; width?: number | string; radius?: number }) {
  return <div className={s.skeleton} style={{ height, width, borderRadius: radius }} aria-hidden />;
}
