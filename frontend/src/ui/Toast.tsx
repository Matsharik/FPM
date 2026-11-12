import { CircleAlert, CircleCheck, Info, X } from 'lucide-react';
import { useSyncExternalStore } from 'react';
import s from './ui.module.css';

type ToastTone = 'ok' | 'crit' | 'warn' | 'info';
interface ToastItem {
  id: number;
  text: string;
  tone: ToastTone;
}

let items: ToastItem[] = [];
let seq = 0;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((fn) => fn());

export function toast(text: string, tone: ToastTone = 'ok', ms = 5000): void {
  const id = ++seq;
  items = [...items, { id, text, tone }].slice(-4);
  emit();
  window.setTimeout(() => dismiss(id), ms);
}

function dismiss(id: number) {
  items = items.filter((t) => t.id !== id);
  emit();
}

export function Toaster() {
  const list = useSyncExternalStore(
    (fn) => {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    () => items,
  );
  return (
    <div className={s.toasts} role="status" aria-live="polite">
      {list.map((t) => {
        const Icon = t.tone === 'ok' ? CircleCheck : t.tone === 'info' ? Info : CircleAlert;
        return (
          <div key={t.id} className={s.toast}>
            <Icon size={18} className={s[`toastIcon-${t.tone}`]} aria-hidden />
            <span>{t.text}</span>
            <button type="button" className={s.toastClose} onClick={() => dismiss(t.id)} aria-label="Закрыть">
              <X size={16} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
