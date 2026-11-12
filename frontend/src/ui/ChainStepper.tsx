// Сигнал → Контекст → Причина → Действие → Проверка. Шаги — якоря секций карточки.
import { Check } from 'lucide-react';
import s from './ui.module.css';

export const CHAIN_STEPS = [
  { key: 'signal', label: 'Сигнал' },
  { key: 'context', label: 'Контекст' },
  { key: 'cause', label: 'Причина' },
  { key: 'action', label: 'Действие' },
  { key: 'check', label: 'Проверка' },
] as const;

export type ChainKey = (typeof CHAIN_STEPS)[number]['key'];

/** current — индекс текущего шага (0..4); 5 — цепочка пройдена целиком. */
export function ChainStepper({ current, onStep }: { current: number; onStep?: (key: ChainKey) => void }) {
  return (
    <ol className={s.chain} aria-label="Путь решения">
      {CHAIN_STEPS.map((step, i) => {
        const state = i < current ? 'done' : i === current ? 'current' : 'todo';
        const cls = state === 'done' ? s.chainDone : state === 'current' ? s.chainCurrent : '';
        return (
          <li key={step.key} className={`${s.chainStep} ${cls}`}>
            <a
              className={s.chainLink}
              href={`#${step.key}`}
              aria-current={state === 'current' ? 'step' : undefined}
              onClick={(e) => {
                if (!onStep) return;
                e.preventDefault();
                onStep(step.key);
              }}
            >
              <span className={s.chainNum}>{state === 'done' ? <Check size={14} strokeWidth={3} /> : i + 1}</span>
              {step.label}
            </a>
          </li>
        );
      })}
    </ol>
  );
}
