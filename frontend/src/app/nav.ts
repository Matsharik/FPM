// Навигация с сохранением глобального состояния URL: units= и as= переносятся во все ссылки.
import { useCallback, useSyncExternalStore } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router';
import type { Units } from '../api/types';
import { getSelf, getUser, isViewingAs, subscribeUser } from '../session/user';

export type Params = Record<string, string | number | null | undefined | false>;

export function useUnits(): Units {
  const [sp] = useSearchParams();
  return sp.get('units') === 'relative' ? 'relative' : 'natural';
}

export function useCurrentUser(): string | null {
  return useSyncExternalStore(subscribeUser, getUser, getUser);
}

export function useSelfUser(): string | null {
  return useSyncExternalStore(subscribeUser, getSelf, getSelf);
}

function build(path: string, params: Params, units: Units): string {
  const [base, existing] = path.split('?');
  const sp = new URLSearchParams(existing ?? '');
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === false || v === '') sp.delete(k);
    else sp.set(k, String(v));
  }
  if (units === 'relative' && !sp.has('units')) sp.set('units', 'relative');
  const as = isViewingAs() ? getUser() : null;
  if (as && !sp.has('as')) sp.set('as', as);
  const qs = sp.toString();
  return qs ? `${base}?${qs}` : base;
}

/** Ссылка на маршрут с переносом units/as. */
export function useLinkTo() {
  const units = useUnits();
  useCurrentUser(); // перерисовка при смене пользователя
  return useCallback((path: string, params: Params = {}) => build(path, params, units), [units]);
}

export function useGo() {
  const navigate = useNavigate();
  const linkTo = useLinkTo();
  return useCallback(
    (path: string, params: Params = {}, opts?: { replace?: boolean }) => navigate(linkTo(path, params), opts),
    [navigate, linkTo],
  );
}

/** Ссылка «этот же экран, но с другими параметрами» (панель инспектора, фильтры). */
export function useHereLink() {
  const location = useLocation();
  const linkTo = useLinkTo();
  return useCallback(
    (params: Params) => linkTo(`${location.pathname}${location.search}`, params),
    [location.pathname, location.search, linkTo],
  );
}

export function useSetParams() {
  const navigate = useNavigate();
  const here = useHereLink();
  return useCallback(
    (params: Params, opts?: { replace?: boolean }) => navigate(here(params), opts),
    [navigate, here],
  );
}
