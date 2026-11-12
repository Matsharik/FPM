// Вход (5.1): выбор демо-пользователя и матрица прав «пользователи × права».
import { Check, Minus } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router';
import { useAllMe, useUsers } from '../../api/hooks';
import type { Me, User } from '../../api/types';
import { Logo, PRODUCT_NAME, PRODUCT_TAGLINE } from '../../brand';
import { PERMISSIONS, levelLabel } from '../../lib/permissions';
import { getUser, setUser } from '../../session/user';
import { homeFor } from '../../shell/Shell';
import { ErrorState, Skeleton } from '../../ui/States';
import s from './login.module.css';

const REASONS: Record<string, string> = {
  unauthorized: 'Пользователь не выбран. Выберите, под кем работать.',
  unknown_user: 'Такого пользователя на стенде нет (возможно, стенд сброшен). Выберите пользователя снова.',
};

function zoneText(u: User): string {
  const roots = u.scope_roots.map((r) => r.name).join(', ');
  return roots ? `Зона: ${roots}` : 'Зона не задана';
}

function initials(name: string): string {
  return name
    .replace(/[.«»]/g, '')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join('');
}

export function Login() {
  const users = useUsers();
  const navigate = useNavigate();
  const [sp] = useSearchParams();
  const reason = sp.get('reason');
  const logins = users.data?.map((u) => u.login) ?? [];
  const meList = useAllMe(logins);
  const meBy = new Map<string, Me>();
  meList.forEach((q, i) => {
    if (q.data) meBy.set(logins[i], q.data);
  });
  const current = getUser();

  const choose = (u: User) => {
    setUser(u.login);
    navigate(homeFor(u));
  };

  return (
    <div className={s.page}>
      <header className={s.hero}>
        <Logo size={56} />
        <div>
          <h1 className={s.title}>{PRODUCT_NAME}</h1>
          <p className={s.tagline}>{PRODUCT_TAGLINE}</p>
        </div>
      </header>

      {reason && REASONS[reason] ? <div className={s.reason}>{REASONS[reason]}</div> : null}

      <section aria-labelledby="who">
        <div className={s.sectionHead}>
          <h2 id="who">Под кем войти</h2>
          <p className={s.note}>В продакшне здесь вход через SSO/AD; в демо пароль не нужен.</p>
        </div>
        {users.isError ? (
          <ErrorState error={users.error} onRetry={() => users.refetch()} />
        ) : (
          <div className={s.cards}>
            {users.isPending
              ? Array.from({ length: 5 }, (_, i) => <Skeleton key={i} height={172} radius={16} />)
              : users.data.map((u) => {
                  const me = meBy.get(u.login);
                  return (
                    <button key={u.login} type="button" className={`${s.card} ${u.login === current ? s.cardCurrent : ''}`} onClick={() => choose(u)}>
                      <span className={s.avatar} aria-hidden>
                        {initials(u.name)}
                      </span>
                      <span className={s.cardName}>{u.name}</span>
                      <span className={s.cardLevel}>{me ? levelLabel(me.role, me.sees_everything) : levelLabel(u.role)}</span>
                      <span className={s.cardZone}>{zoneText(u)}</span>
                      {u.node ? <span className={s.cardZone}>Свой узел: {u.node.name}</span> : null}
                      {me ? <span className={s.cardMeta}>Узлов в зоне: {me.zone.length}</span> : null}
                    </button>
                  );
                })}
          </div>
        )}
      </section>

      <section aria-labelledby="rights" className={s.matrixSection}>
        <div className={s.sectionHead}>
          <h2 id="rights">Единые права</h2>
          <p className={s.note}>Права приходят с сервера для каждого пользователя; интерфейс показывает только разрешённые действия.</p>
        </div>
        <div className={s.matrixWrap}>
          <table className={s.matrix}>
            <thead>
              <tr>
                <th scope="col">Право</th>
                {(users.data ?? []).map((u) => (
                  <th key={u.login} scope="col">
                    <span className={s.thName}>{u.name}</span>
                    <span className={s.thLevel}>{meBy.get(u.login) ? levelLabel(u.role, meBy.get(u.login)?.sees_everything) : levelLabel(u.role)}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {PERMISSIONS.map((p) => (
                <tr key={p.key}>
                  <th scope="row">
                    <span className={s.permName}>{p.label}</span>
                    <span className={s.permOpens}>{p.opens}</span>
                  </th>
                  {(users.data ?? []).map((u) => {
                    const me = meBy.get(u.login);
                    const has = me?.permissions.includes(p.key);
                    return (
                      <td key={u.login}>
                        {me === undefined ? (
                          <span className={s.cellNo}>…</span>
                        ) : has ? (
                          <span className={s.cellYes} aria-label="есть">
                            <Check size={16} strokeWidth={3} />
                          </span>
                        ) : (
                          <span className={s.cellNo} aria-label="нет">
                            <Minus size={16} />
                          </span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
              <tr>
                <th scope="row">
                  <span className={s.permName}>Читать свою зону</span>
                  <span className={s.permOpens}>Пульс, структура, решения, заказы, журнал — в пределах зоны</span>
                </th>
                {(users.data ?? []).map((u) => (
                  <td key={u.login}>
                    <span className={s.cellYes} aria-label="есть">
                      <Check size={16} strokeWidth={3} />
                    </span>
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
