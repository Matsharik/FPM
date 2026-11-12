import { useQueryClient } from '@tanstack/react-query';
import {
  Activity,
  BookOpen,
  ClipboardCheck,
  Database,
  Eye,
  ListTodo,
  LogOut,
  Package,
  ScrollText,
  ServerCrash,
  Users,
  Workflow,
  Wrench,
  type LucideIcon,
} from 'lucide-react';
import { useEffect, useRef } from 'react';
import { Link, NavLink, Navigate, Outlet, useLocation, useNavigate, useSearchParams } from 'react-router';
import { useClock, useMe, useUsers } from '../api/hooks';
import { useNetworkDown } from '../api/netStatus';
import type { Me } from '../api/types';
import { useCurrentUser, useLinkTo, useSelfUser, useSetParams, useUnits } from '../app/nav';
import { Logo, PRODUCT_NAME } from '../brand';
import { can, levelLabel } from '../lib/permissions';
import { enterAs, getUser, isViewingAs, returnToSelf, setUser } from '../session/user';
import { MenuItem, MenuNote, MenuSep, Popover } from '../ui/Floating';
import { Segmented } from '../ui/Segmented';
import { ChangesPanel } from './ChangesPanel';
import { DemoClock } from './DemoClock';
import { InspectorHost } from './InspectorHost';
import s from './shell.module.css';

interface NavDef {
  to: string;
  label: string;
  icon: LucideIcon;
  show?: (me: Me) => boolean;
}

const NAV: NavDef[] = [
  { to: '/pulse', label: 'Пульс', icon: Activity },
  { to: '/tree', label: 'Структура', icon: Workflow },
  { to: '/deviations', label: 'Решения', icon: ClipboardCheck },
  { to: '/orders', label: 'Заказы', icon: Package },
  { to: '/team', label: 'Команда', icon: Users, show: (me) => can(me.permissions, 'people.read') },
  { to: '/queue', label: 'Моя смена', icon: ListTodo, show: (me) => me.role === 'qc' },
  { to: '/sources', label: 'Источники', icon: Database },
  { to: '/glossary', label: 'Словарь', icon: BookOpen },
  { to: '/audit', label: 'Журнал', icon: ScrollText },
  { to: '/tree?mode=build', label: 'Конструктор', icon: Wrench, show: (me) => can(me.permissions, 'structure.write') },
];

export const ROUTE_TITLES: Record<string, string> = {
  pulse: 'Пульс',
  tree: 'Структура',
  deviations: 'Решения',
  orders: 'Заказы',
  team: 'Команда',
  queue: 'Моя смена',
  sources: 'Источники',
  glossary: 'Словарь',
  audit: 'Журнал',
  ui: 'Дизайн-система',
};

/** Домашний экран по роли: admin → Пульс; qc → Моя смена (до Ф5 — Пульс); builder → Структура. */
export function homeFor(me: Pick<Me, 'role'>): string {
  if (me.role === 'builder') return '/tree';
  return '/pulse';
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

function Crumbs() {
  const location = useLocation();
  const linkTo = useLinkTo();
  const [sp] = useSearchParams();
  const parts = location.pathname.split('/').filter(Boolean);
  const root = parts[0] ?? 'pulse';
  const title = root === 'tree' && sp.get('mode') === 'build' ? 'Конструктор' : ROUTE_TITLES[root] ?? root;
  return (
    <nav className={s.crumbs} aria-label="Где я">
      {parts.length > 1 ? (
        <>
          <Link to={linkTo(`/${root}`)}>{title}</Link>
          <span aria-hidden>/</span>
          <span className={s.crumbCurrent}>{decodeURIComponent(parts.slice(1).join(' / '))}</span>
        </>
      ) : (
        <span className={s.crumbCurrent}>{title}</span>
      )}
    </nav>
  );
}

function UnitsToggle() {
  const units = useUnits();
  const setParams = useSetParams();
  return (
    <Segmented
      label="Единицы"
      value={units}
      options={[
        { value: 'natural', label: 'Натуральные' },
        { value: 'relative', label: '% к цели' },
      ]}
      onChange={(v) => setParams({ units: v === 'relative' ? 'relative' : null }, { replace: true })}
    />
  );
}

function UserChip({ me }: { me: Me }) {
  const users = useUsers();
  const navigate = useNavigate();
  const viewingAs = isViewingAs();
  return (
    <Popover
      role="menu"
      placement="bottom-end"
      trigger={
        <button type="button" className={s.userChip} aria-label={`Пользователь: ${me.name}. Сменить пользователя`}>
          <span className={s.avatar} aria-hidden>
            {initials(me.name)}
          </span>
          <span style={{ minWidth: 0 }}>
            <span className={s.userName}>{me.name}</span>
            <span className={s.userLevel}>{levelLabel(me.role, me.sees_everything)}</span>
          </span>
        </button>
      }
    >
      {(close) => (
        <>
          <MenuNote>{viewingAs ? 'Вкладка открыта глазами другого пользователя' : 'Сменить пользователя во вкладке'}</MenuNote>
          {(users.data ?? []).map((u) => (
            <MenuItem
              key={u.login}
              active={u.login === me.login}
              onClick={() => {
                close();
                setUser(u.login);
                navigate('/');
              }}
            >
              {u.name}
            </MenuItem>
          ))}
          <MenuSep />
          <MenuItem
            icon={<LogOut size={16} />}
            onClick={() => {
              close();
              navigate('/login');
            }}
          >
            К выбору пользователя
          </MenuItem>
        </>
      )}
    </Popover>
  );
}

function Banners() {
  const down = useNetworkDown();
  const qc = useQueryClient();
  const self = useSelfUser();
  const user = useCurrentUser();
  const users = useUsers();
  const navigate = useNavigate();
  const location = useLocation();
  const viewingAs = !!self && self !== user;
  const name = (login: string | null) => users.data?.find((u) => u.login === login)?.name ?? login;
  return (
    <div className={s.bannerWrap}>
      {down ? (
        <div className={`${s.banner} ${s.bannerDown}`} role="alert">
          <ServerCrash size={18} aria-hidden />
          <span>
            Сервер не отвечает. Запустите его командой <span className={s.bannerCode}>python run.py</span> и повторите.
          </span>
          <button type="button" className="btn btn-outline btn-sm" style={{ marginLeft: 'auto' }} onClick={() => qc.refetchQueries()}>
            Повторить
          </button>
        </div>
      ) : null}
      {viewingAs ? (
        <div className={`${s.banner} ${s.bannerAs}`}>
          <Eye size={18} aria-hidden />
          <span>
            Вы смотрите как: <b>{name(user)}</b>
          </span>
          <button
            type="button"
            className="btn btn-outline btn-sm"
            style={{ marginLeft: 'auto', color: 'var(--text)' }}
            onClick={() => {
              returnToSelf();
              const sp = new URLSearchParams(location.search);
              sp.delete('as');
              navigate(sp.toString() ? `${location.pathname}?${sp}` : location.pathname);
            }}
          >
            Вернуться к себе ({name(self)})
          </button>
        </div>
      ) : null}
    </div>
  );
}

/** Часы мог сдвинуть другой пользователь или вкладка: при смене «сейчас» перечитываем всё. */
function ClockWatcher() {
  const clock = useClock();
  const qc = useQueryClient();
  const prev = useRef<string | null>(null);
  useEffect(() => {
    const now = clock.data?.now;
    if (!now) return;
    if (prev.current && prev.current !== now) qc.invalidateQueries({ predicate: (q) => q.queryKey[1] !== 'clock' });
    prev.current = now;
  }, [clock.data?.now, qc]);
  return null;
}

/** ?as=<login> в URL: вкладка открывается глазами другого пользователя. */
function AsParamWatcher() {
  const [sp] = useSearchParams();
  const as = sp.get('as');
  useEffect(() => {
    if (as && as !== getUser()) enterAs(as);
  }, [as]);
  return null;
}

export function Shell() {
  const user = useCurrentUser();
  const me = useMe();
  const linkTo = useLinkTo();
  const location = useLocation();
  const [sp] = useSearchParams();
  if (!user) return <Navigate to="/login" replace />;
  const meData = me.data;
  const buildMode = sp.get('mode') === 'build';
  return (
    <div className={s.app}>
      <AsParamWatcher />
      <ClockWatcher />
      <header className={s.top}>
        <Link to={linkTo(meData ? homeFor(meData) : '/pulse')} className={s.brand} aria-label={PRODUCT_NAME}>
          <Logo size={32} />
          <span className={s.brandName}>{PRODUCT_NAME}</span>
        </Link>
        <Crumbs />
        <div className={s.topRight}>
          <UnitsToggle />
          <DemoClock />
          {meData ? <UserChip me={meData} /> : null}
        </div>
      </header>
      <Banners />
      <nav className={s.nav} aria-label="Разделы">
        {NAV.filter((n) => !meData || !n.show || n.show(meData)).map((n) => {
          const [path, query] = n.to.split('?');
          const isBuild = query === 'mode=build';
          const active = location.pathname.startsWith(path) && (path !== '/tree' || buildMode === isBuild);
          return (
            <NavLink
              key={n.to}
              to={linkTo(path, isBuild ? { mode: 'build' } : {})}
              className={`${s.navItem} ${active ? s.navActive : ''}`}
              aria-current={active ? 'page' : undefined}
            >
              <span className={s.navIcon}>
                <n.icon size={20} aria-hidden />
              </span>
              {n.label}
            </NavLink>
          );
        })}
      </nav>
      <main className={s.main} id="main">
        <Outlet />
      </main>
      <InspectorHost />
      <ChangesPanel />
    </div>
  );
}

export function Page({ children }: { children: React.ReactNode }) {
  return <div className={s.page}>{children}</div>;
}
