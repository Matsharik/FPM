// Панель «Что изменилось» после перемотки демо-времени (5.15).
import { History, X } from 'lucide-react';
import { Link } from 'react-router';
import { closeChanges, useChanges } from '../api/deviationHooks';
import { useLinkTo } from '../app/nav';
import { plural } from '../lib/format';
import { DevRef } from '../ui/Refs';
import s from './shell.module.css';

export function ChangesPanel() {
  const c = useChanges();
  const linkTo = useLinkTo();
  if (!c) return null;
  const nothing = !c.items.length && !c.created.length && !c.ready.length;
  return (
    <aside className={s.changes} aria-label="Что изменилось">
      <div className={s.changesHead}>
        <History size={18} aria-hidden />
        <b>
          За {c.days} {plural(c.days, ['день', 'дня', 'дней'])} демо-времени
        </b>
        <button type="button" className={s.changesClose} onClick={closeChanges} aria-label="Закрыть">
          <X size={16} />
        </button>
      </div>
      {nothing ? <p className="muted">Статусы плиток и решений не изменились.</p> : null}
      <ul className={s.changesList}>
        {c.items.map((i) => (
          <li key={i.text}>{i.link ? <Link to={linkTo(i.link.path, i.link.params)} onClick={closeChanges}>{i.text}</Link> : i.text}</li>
        ))}
        {c.created.length ? (
          <li>
            Новых отклонений: {c.created.length}{' '}
            {c.created.map((id) => (
              <DevRef key={id} id={id} />
            ))}
          </li>
        ) : null}
        {c.ready.map((d) => (
          <li key={d.id}>
            <DevRef id={d.id} /> можно перепроверять
          </li>
        ))}
      </ul>
      {c.branches.length ? <p className={s.changesNote}>сценарные данные: ветка «{c.branches.join('», «')}»</p> : null}
    </aside>
  );
}
