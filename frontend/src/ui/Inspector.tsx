// Оболочка правой панели: «←» (назад по истории), заголовок, закрыть, изменяемая ширина 420–560.
import { ArrowLeft, X } from 'lucide-react';
import { useCallback, useRef, type ReactNode } from 'react';
import s from './ui.module.css';

const MIN_W = 420;
const MAX_W = 560;
const KEY = 'fpm.inspectorWidth';

export function readInspectorWidth(): number {
  try {
    const v = Number(localStorage.getItem(KEY));
    if (v >= MIN_W && v <= MAX_W) return v;
  } catch {
    /* нет хранилища */
  }
  return 460;
}

export function InspectorShell({
  kicker,
  title,
  status,
  actions,
  onBack,
  onClose,
  onResize,
  children,
}: {
  kicker?: ReactNode;
  title: ReactNode;
  status?: ReactNode;
  actions?: ReactNode;
  onBack?: () => void;
  onClose?: () => void;
  onResize?: (w: number) => void;
  children: ReactNode;
}) {
  const startRef = useRef<{ x: number; w: number } | null>(null);
  const onPointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      const panel = e.currentTarget.parentElement;
      if (!panel || !onResize) return;
      startRef.current = { x: e.clientX, w: panel.getBoundingClientRect().width };
      e.currentTarget.setPointerCapture(e.pointerId);
    },
    [onResize],
  );
  const onPointerMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (!startRef.current || !onResize) return;
      const w = Math.min(MAX_W, Math.max(MIN_W, startRef.current.w + (startRef.current.x - e.clientX)));
      onResize(w);
    },
    [onResize],
  );
  const onPointerUp = useCallback(() => {
    startRef.current = null;
  }, []);
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!onResize) return;
    const panel = (e.currentTarget as HTMLElement).parentElement;
    const w = panel?.getBoundingClientRect().width ?? 460;
    if (e.key === 'ArrowLeft') onResize(Math.min(MAX_W, w + 20));
    if (e.key === 'ArrowRight') onResize(Math.max(MIN_W, w - 20));
  };
  return (
    <aside className={s.inspector} aria-label="Инспектор">
      {onResize ? (
        <div
          className={s.resizer}
          role="separator"
          aria-orientation="vertical"
          aria-label="Изменить ширину панели"
          tabIndex={0}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onKeyDown={onKeyDown}
        />
      ) : null}
      <div className={s.inspectorHead}>
        {onBack ? (
          <button type="button" className={s.iconBtn} onClick={onBack} aria-label="Назад">
            <ArrowLeft size={18} />
          </button>
        ) : null}
        <div className={s.inspectorTitles}>
          {kicker ? <div className={s.inspectorKicker}>{kicker}</div> : null}
          <div className={s.inspectorTitle}>{title}</div>
          {status ? <div style={{ marginTop: 8 }}>{status}</div> : null}
        </div>
        {onClose ? (
          <button type="button" className={s.iconBtn} onClick={onClose} aria-label="Закрыть панель">
            <X size={18} />
          </button>
        ) : null}
      </div>
      {actions ? <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, padding: '12px 16px', borderBottom: '1px solid var(--border)' }}>{actions}</div> : null}
      <div className={s.inspectorBody}>{children}</div>
    </aside>
  );
}

export function saveInspectorWidth(w: number) {
  try {
    localStorage.setItem(KEY, String(Math.round(w)));
  } catch {
    /* нет хранилища */
  }
}
