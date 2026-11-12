// Виджет демо-времени (5.15). Без права demo.control — только показ.
import { CalendarClock, ChevronDown, FastForward, RotateCcw } from 'lucide-react';
import { useState } from 'react';
import { closeChanges, useAdvanceWithChanges } from '../api/deviationHooks';
import { useClock, useMe, useReset } from '../api/hooks';
import { can } from '../lib/permissions';
import { fmtClock } from '../lib/time';
import { ConfirmDialog } from '../ui/ConfirmDialog';
import { MenuItem, MenuNote, MenuSep, Popover, Tooltip } from '../ui/Floating';
import { toast } from '../ui/Toast';
import { useGo } from '../app/nav';
import { plural } from '../lib/format';
import s from './shell.module.css';

const HINT = 'Часы стенда стоят, время двигает только перемотка';

export function DemoClockView({ now, moved, interactive }: { now: string; moved?: boolean; interactive?: boolean }) {
  return (
    <>
      <CalendarClock size={18} aria-hidden />
      <span>
        <span className={s.clockLabel}>Демо-время</span>
        <span className={s.clockValue}>{fmtClock(now)}</span>
      </span>
      {interactive ? <ChevronDown size={16} aria-hidden /> : null}
      {moved ? <span className="visually-hidden">часы сдвинуты от исходного времени</span> : null}
    </>
  );
}

export function DemoClock() {
  const clock = useClock();
  const me = useMe();
  const advance = useAdvanceWithChanges();
  const reset = useReset();
  const go = useGo();
  const [confirmReset, setConfirmReset] = useState(false);
  const [custom, setCustom] = useState('3');
  if (!clock.data) return null;
  const moved = clock.data.now !== clock.data.default_now;
  const control = can(me.data?.permissions, 'demo.control');

  const doAdvance = (days: number, close: () => void) => {
    close();
    advance.mutate(days, {
      onSuccess: ({ r }) => {
        toast(`Демо-время перемотано на ${days} ${plural(days, ['день', 'дня', 'дней'])}: ${fmtClock(r.now)}.`, 'info');
      },
      onError: (e) => toast((e as Error).message, 'crit'),
    });
  };

  if (!control) {
    return (
      <Tooltip content={HINT}>
        <div className={`${s.clock} ${s.clockStatic} ${moved ? s.clockMoved : ''}`} tabIndex={0}>
          <DemoClockView now={clock.data.now} moved={moved} />
        </div>
      </Tooltip>
    );
  }

  return (
    <>
      <Popover
        role="menu"
        placement="bottom-end"
        trigger={
          <button type="button" className={`${s.clock} ${moved ? s.clockMoved : ''}`} aria-label={`Демо-время ${fmtClock(clock.data.now)}. ${HINT}`} title={HINT}>
            <DemoClockView now={clock.data.now} moved={moved} interactive />
          </button>
        }
      >
        {(close) => (
          <>
            <MenuNote>{HINT}</MenuNote>
            <MenuItem icon={<FastForward size={16} />} onClick={() => doAdvance(1, close)}>
              +1 день
            </MenuItem>
            <MenuItem icon={<FastForward size={16} />} onClick={() => doAdvance(7, close)}>
              +7 дней
            </MenuItem>
            <form
              className={s.customDays}
              onSubmit={(e) => {
                e.preventDefault();
                const n = Math.round(Number(custom));
                if (n >= 1 && n <= 60) doAdvance(n, close);
              }}
            >
              <label htmlFor="adv-days">Своё:</label>
              <input id="adv-days" type="number" min={1} max={60} value={custom} onChange={(e) => setCustom(e.target.value)} />
              <span className="muted">дн. (1–60)</span>
              <button type="submit" className="btn btn-outline btn-sm">
                Перемотать
              </button>
            </form>
            <MenuSep />
            <MenuItem
              icon={<RotateCcw size={16} />}
              onClick={() => {
                close();
                setConfirmReset(true);
              }}
            >
              Сброс стенда
            </MenuItem>
          </>
        )}
      </Popover>
      <ConfirmDialog
        open={confirmReset}
        title="Сбросить стенд?"
        text="Удалятся решения, отметки и правки конструктора; стенд вернётся к исходному состоянию."
        confirmLabel="Сбросить стенд"
        danger
        busy={reset.isPending}
        onCancel={() => setConfirmReset(false)}
        onConfirm={() =>
          reset.mutate(undefined, {
            onSuccess: (r) => {
              setConfirmReset(false);
              closeChanges();
              toast(`Стенд сброшен: ${fmtClock(r.now)}, карточки: ${r.deviations.join(', ') || 'нет'}.`, 'ok');
              go('/');
            },
            onError: (e) => toast((e as Error).message, 'crit'),
          })
        }
      />
    </>
  );
}
