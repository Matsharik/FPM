// Запросы TanStack Query. Ключ всегда начинается с логина: у каждого пользователя свой кэш.
// GET /api/nodes/{id} и /api/deviations/{id} пишут журнал — их нет здесь в префетче и
// они не перечитываются по фокусу окна (см. useNodeDetail в Ф2).
import { QueryClient, useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCurrentUser, useUnits } from '../app/nav';
import { api, ApiError, NetworkError } from './client';
import type {
  Advance,
  AuditOut,
  Clock,
  Contributions,
  Forecast,
  Glossary,
  Graph,
  KpiCard,
  KpiSeries,
  Me,
  NodeDetail,
  Overview,
  PeopleOut,
  Portfolio,
  ResetOut,
  Source,
  Trace,
  User,
} from './types';
import { setNetworkDown } from './netStatus';

export function makeQueryClient(onAuthError: (code: string) => void): QueryClient {
  const handle = (err: unknown) => {
    if (err instanceof NetworkError) setNetworkDown(true);
    if (err instanceof ApiError && (err.code === 'unauthorized' || err.code === 'unknown_user')) onAuthError(err.code);
  };
  const qc = new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 10_000,
        refetchOnWindowFocus: true,
        retry: (count, err) => err instanceof NetworkError && count < 1,
      },
      mutations: { retry: false },
    },
  });
  qc.getQueryCache().subscribe((ev) => {
    if (ev.type !== 'updated') return;
    const st = ev.query.state;
    if (ev.action.type === 'error') handle(st.error);
    if (ev.action.type === 'success') setNetworkDown(false);
  });
  qc.getMutationCache().subscribe((ev) => {
    if (ev.type === 'updated' && ev.action.type === 'error') handle(ev.mutation?.state.error);
  });
  return qc;
}

export function useUsers() {
  return useQuery({ queryKey: ['users'], queryFn: () => api<User[]>('/api/auth/users'), staleTime: 60_000 });
}

export function useMe() {
  const user = useCurrentUser();
  return useQuery({ queryKey: [user, 'me'], queryFn: () => api<Me>('/api/me', { as: user ?? undefined }), enabled: !!user, staleTime: 60_000 });
}

/** Профили всех пользователей — для матрицы прав на входе (GET /api/me под каждым логином). */
export function useAllMe(logins: string[]) {
  return useQueries({
    queries: logins.map((login) => ({
      queryKey: [login, 'me'],
      queryFn: () => api<Me>('/api/me', { as: login }),
      staleTime: 60_000,
    })),
  });
}

/** Демо-часы: лёгкий опрос раз в 30 с (часы может сдвинуть другая вкладка). */
export function useClock() {
  const user = useCurrentUser();
  return useQuery({
    queryKey: [user, 'clock'],
    queryFn: () => api<Clock>('/api/demo/clock', { as: user ?? undefined }),
    enabled: !!user,
    refetchInterval: 30_000,
  });
}

export function useOverview() {
  const user = useCurrentUser();
  const units = useUnits();
  return useQuery({
    queryKey: [user, 'overview', units],
    queryFn: () => api<Overview>('/api/overview', { query: { units }, as: user ?? undefined }),
    enabled: !!user,
  });
}

export function useSources() {
  const user = useCurrentUser();
  return useQuery({ queryKey: [user, 'sources'], queryFn: () => api<Source[]>('/api/sources', { as: user ?? undefined }), enabled: !!user, staleTime: 60_000 });
}

export function useGlossary() {
  const user = useCurrentUser();
  return useQuery({ queryKey: [user, 'glossary'], queryFn: () => api<Glossary>('/api/glossary', { as: user ?? undefined }), enabled: !!user, staleTime: 60_000 });
}

export interface SeriesReq {
  nodeId: number;
  kpi: string;
  from?: string;
  to?: string;
  agg?: 'day' | 'raw';
}

function seriesQuery(user: string | null, units: string, r: SeriesReq) {
  return {
    queryKey: [user, 'series', r.nodeId, r.kpi, r.from ?? null, r.to ?? null, r.agg ?? 'day', units],
    queryFn: () =>
      api<KpiSeries>(`/api/kpi/${r.nodeId}/${encodeURIComponent(r.kpi)}`, {
        query: { from: r.from, to: r.to, agg: r.agg ?? 'day', units },
        as: user ?? undefined,
      }),
    enabled: !!user,
  };
}

export function useSeriesMany(reqs: Array<SeriesReq | null>) {
  const user = useCurrentUser();
  const units = useUnits();
  return useQueries({
    queries: reqs.map((r) =>
      r
        ? seriesQuery(user, units, r)
        : { queryKey: [user, 'series', 'none'], queryFn: () => Promise.resolve(null), enabled: false },
    ),
  });
}

export function useSeries(r: SeriesReq | null) {
  const user = useCurrentUser();
  const units = useUnits();
  return useQuery(r ? seriesQuery(user, units, r) : { queryKey: [user, 'series', 'none'], queryFn: () => Promise.resolve(null), enabled: false });
}

type Q = Record<string, string | number | boolean | null | undefined>;

/** Обычный GET с ключом [логин, путь, параметры]. */
function useGet<T>(path: string | null, query: Q = {}, opts: { staleTime?: number; journal?: boolean } = {}) {
  const user = useCurrentUser();
  return useQuery({
    queryKey: [user, path, query],
    queryFn: () => api<T>(path!, { query, as: user ?? undefined }),
    enabled: !!user && !!path,
    staleTime: opts.journal ? Infinity : opts.staleTime,
    // Открытия узла и карточки пишутся в журнал: по фокусу окна их не перечитываем.
    refetchOnWindowFocus: !opts.journal,
  });
}

export function useGraph() {
  const units = useUnits();
  return useGet<Graph>('/api/graph', { units });
}

/** GET /api/nodes/{id} — пишет «открыл узел» в журнал: только по явному открытию. */
export function useNodeDetail(id: number | null) {
  return useGet<NodeDetail>(id === null ? null : `/api/nodes/${id}`, {}, { journal: true });
}

export function useNodeKpis(id: number | null) {
  const units = useUnits();
  return useGet<KpiCard[]>(id === null ? null : `/api/nodes/${id}/kpis`, { units });
}

export function useContributions(nodeId: number | null, kpi: string | null) {
  return useGet<Contributions>(nodeId === null || !kpi ? null : '/api/analysis/contributions', { node: nodeId, kpi: kpi ?? '' });
}

export function useForecast(nodeId: number | null, kpi: string | null, horizon: number | null) {
  const units = useUnits();
  return useGet<Forecast>(nodeId === null || !kpi || !horizon ? null : `/api/kpi/${nodeId}/${encodeURIComponent(kpi ?? '')}/forecast`, { horizon, units });
}

export function useDeviations(filter: { node?: number; status?: string; owner?: string } = {}) {
  return useGet<Portfolio>('/api/deviations', filter);
}

export function useAudit(filter: Q, enabled = true) {
  return useGet<AuditOut>(enabled ? '/api/audit' : null, filter);
}

export function useTraceQuery(t: { node: number; kpi: string } | null) {
  return useGet<Trace>(t ? '/api/analysis/trace' : null, t ? { node: t.node, kpi: t.kpi } : {});
}

export function usePeople(nodeId: number | null, enabled: boolean) {
  const units = useUnits();
  return useGet<PeopleOut>(enabled && nodeId !== null ? `/api/nodes/${nodeId}/people` : null, { units });
}

/** Перемотка и сброс демо-времени: после них перечитываются ВСЕ запросы. */
export function useAdvance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (days: number) => api<Advance>('/api/demo/advance', { method: 'POST', query: { days } }),
    onSuccess: () => qc.invalidateQueries(),
  });
}

export function useReset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<ResetOut>('/api/demo/reset', { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries(),
  });
}
