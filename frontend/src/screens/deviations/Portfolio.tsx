// Решения — портфель (5.7): сводка и список по жизненному циклу.
import { ChevronDown, ChevronRight } from 'lucide-react';
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { useClock, useDeviations, useGraph, useUsers } from '../../api/hooks';
import type { Deviation } from '../../api/types';
import { useLinkTo, useSetParams } from '../../app/nav';
import { fmtNum, fmtShare } from '../../lib/format';
import { DEVIATION_STATUS } from '../../lib/status';
import { MIN_RECHECK_DAYS } from '../../lib/transitions';
import { daysBetween, fmtDateTime } from '../../lib/time';
import { Page } from '../../shell/Shell';
import { EmptyState, ErrorState, Skeleton } from '../../ui/States';
import { KpiLink, NodeLink } from '../../ui/Refs';
import { DeviationStatusBadge, StatusBadge } from '../../ui/Status';
import s from './portfolio.module.css';

interface Group {
  key: string;
  title: string;
  hint: string;
  test: (d: Deviation, now: string) => boolean;
}

const waiting = (d: Deviation, now: string) =>
  d.status === 'done' ||
  ((d.status === 'assigned' || d.status === 'in_progress') && !!d.action?.assigned_at && daysBetween(d.action.assigned_at, now) >= MIN_RECHECK_DAYS);

const GROUPS: Group[] = [
  { key: 'decide', title: 'Требуют решения', hint: 'открытые и эскалированные', test: (d) => d.status === 'open' || d.status === 'escalated' },
  { key: 'check', title: 'Ждут проверки', hint: `выполнены или прошло не меньше ${MIN_RECHECK_DAYS} суток с назначения`, test: waiting },
  { key: 'work', title: 'В работе', hint: 'назначены, эффект ещё рано проверять', test: (d, now) => (d.status === 'assigned' || d.status === 'in_progress') && !waiting(d, now) },
  { key: 'verified', title: 'Проверено', hint: 'перепроверка подтвердила эффект', test: (d) => d.status === 'verified' },
  { key: 'failed', title: 'Не сработало', hint: 'нужно новое действие', test: (d) => d.status === 'failed' },
  { key: 'closed', title: 'Закрыто', hint: '', test: (d) => d.status === 'closed' },
];

export function Portfolio() {
  const [sp] = useSearchParams();
  const setParams = useSetParams();
  const linkTo = useLinkTo();
  const status = sp.get('status') ?? '';
  const node = sp.get('node') ? Number(sp.get('node')) : undefined;
  const owner = sp.get('owner') ?? '';
  const ids = sp.get('ids')?.split(',').filter(Boolean) ?? [];
  const q = useDeviations({ status: status || undefined, node, owner: owner || undefined });
  const users = useUsers();
  const graph = useGraph();
  const clock = useClock();
  const now = clock.data?.now ?? '';
  const [open, setOpen] = useState<Set<string>>(new Set());
  const items = ((q.data?.items ?? []) as Deviation[]).filter((d) => !ids.length || ids.includes(d.id));
  const sum = q.data?.summary;
  const userName = (l?: string | null) => users.data?.find((u) => u.login === l)?.name ?? l ?? '—';
  const zoneNodes = (graph.data?.nodes ?? []).filter((n) => n.clickable);
  const clickable = new Set(zoneNodes.map((n) => n.id));

  return (
    <Page>
      <h1 style={{ marginBottom: 16 }}>Решения</h1>
      {sum ? (
        <dl className={s.summary}>
          {[
            ['Открыто', sum.open, sum.open ? 'crit' : ''],
            ['Просрочено', sum.overdue, sum.overdue ? 'crit' : ''],
            ['Проверено', sum.verified, sum.verified ? 'ok' : ''],
            ['Не сработало', sum.failed, sum.failed ? 'crit' : ''],
          ].map(([label, v, tone]) => (
            <div key={label as string} className={s.stat}>
              <dt>{label}</dt>
              <dd className={tone ? s[`t-${tone}`] : ''}>{fmtNum(v as number, 0)}</dd>
            </div>
          ))}
          <div className={s.stat}>
            <dt>Успешных перепроверок</dt>
            <dd>{sum.recheck_success_rate === null || sum.recheck_success_rate === undefined ? '—' : fmtShare(sum.recheck_success_rate)}</dd>
          </div>
        </dl>
      ) : null}

      <div className={s.filters}>
        <label>
          Статус
          <select value={status} onChange={(e) => setParams({ status: e.target.value || null })}>
            <option value="">все</option>
            {Object.entries(DEVIATION_STATUS).map(([k, m]) => (
              <option key={k} value={k}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Узел
          <select value={node ?? ''} onChange={(e) => setParams({ node: e.target.value || null })}>
            <option value="">все в зоне</option>
            {zoneNodes.map((n) => (
              <option key={n.id} value={n.id}>
                {n.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Ответственный
          <select value={owner} onChange={(e) => setParams({ owner: e.target.value || null })}>
            <option value="">все</option>
            {(users.data ?? []).map((u) => (
              <option key={u.login} value={u.login}>
                {u.name}
              </option>
            ))}
          </select>
        </label>
        {ids.length ? (
          <span className={s.idsNote}>
            Показаны карточки плитки: {ids.join(', ')}{' '}
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setParams({ ids: null })}>
              показать все
            </button>
          </span>
        ) : null}
      </div>

      {q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : q.isPending ? (
        <Skeleton height={200} radius={16} />
      ) : items.length === 0 ? (
        <EmptyState
          title={status || node || owner ? 'По этому фильтру карточек нет' : 'Карточек решений в вашей зоне нет'}
          text={status || node || owner ? 'Снимите фильтр, чтобы увидеть остальные карточки.' : 'Карточка появляется автоматически, когда показатель пересекает порог.'}
        />
      ) : (
        <div className={s.groups}>
          {GROUPS.map((g) => {
            const list = items.filter((d) => g.test(d, now));
            if (!list.length) {
              return (
                <div key={g.key} className={s.groupEmpty}>
                  {g.title}: <span className="muted">нет</span>
                </div>
              );
            }
            const collapsed = open.has(g.key);
            return (
              <section key={g.key} className={s.group}>
                <button
                  type="button"
                  className={s.groupHead}
                  aria-expanded={!collapsed}
                  onClick={() =>
                    setOpen((o) => {
                      const n = new Set(o);
                      if (n.has(g.key)) n.delete(g.key);
                      else n.add(g.key);
                      return n;
                    })
                  }
                >
                  {collapsed ? <ChevronRight size={18} /> : <ChevronDown size={18} />}
                  <h2>{g.title}</h2>
                  <span className={s.count}>{list.length}</span>
                  {g.hint ? <span className="muted">{g.hint}</span> : null}
                </button>
                {!collapsed ? (
                  <table className={s.table}>
                    <thead>
                      <tr>
                        <th>Карточка</th>
                        <th>Показатель и узел</th>
                        <th>Статус</th>
                        <th>Ответственный</th>
                        <th>Срок</th>
                        <th>Последняя перепроверка</th>
                      </tr>
                    </thead>
                    <tbody>
                      {list.map((d) => {
                        const last = (d.rechecks ?? [])[d.rechecks.length - 1];
                        return (
                          <tr key={d.id}>
                            <td>
                              <Link className={s.devLink} to={linkTo(`/deviations/${d.id}`)}>
                                {d.id}
                              </Link>
                            </td>
                            <td>
                              <KpiLink nodeId={d.node_id} kpi={d.kpi} clickable={clickable.has(d.node_id)}>
                                {d.title}
                              </KpiLink>{' '}
                              ·{' '}
                              <NodeLink id={d.node_id} clickable={clickable.has(d.node_id)}>
                                {d.node_name}
                              </NodeLink>
                            </td>
                            <td>
                              <DeviationStatusBadge status={d.status} size="sm" />
                            </td>
                            <td>{d.action?.owner_login ? userName(d.action.owner_login) : d.action?.owner_node ? `узел ${d.action.owner_node}` : '—'}</td>
                            <td className={s.num}>
                              {d.action?.due_at ? fmtDateTime(d.action.due_at) : '—'}
                              {d.overdue ? <b className={s.t_crit}> · просрочено</b> : null}
                            </td>
                            <td>
                              {!last ? (
                                <span className="muted">не было</span>
                              ) : last.result === 'pending' ? (
                                <span className="muted">рано проверять</span>
                              ) : (
                                <StatusBadge status={last.result === 'passed' ? 'green' : 'red'} size="sm" label={last.result === 'passed' ? 'сработало' : 'не сработало'} />
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                ) : null}
              </section>
            );
          })}
        </div>
      )}
    </Page>
  );
}
