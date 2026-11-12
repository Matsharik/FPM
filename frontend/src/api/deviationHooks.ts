// Карточка отклонения: чтение (пишет «открыл карточку» в журнал — только по явному открытию),
// мутации с аккуратным обновлением кэша (карточку не перечитываем лишний раз), перемотка с «Что изменилось».
import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { useSyncExternalStore } from 'react';
import { useCurrentUser, useUnits } from '../app/nav';
import { diffOverview, readyForRecheck, type ChangeItem, type DevLite, type OverviewSnap } from '../lib/changes';
import { MIN_RECHECK_DAYS } from '../lib/transitions';
import { api } from './client';
import type { Advance, Deviation, Overview, Portfolio } from './types';
import type { components } from './schema';

type Suggest = components['schemas']['SuggestOut'];
type RecheckResult = components['schemas']['RecheckResult'];

export function devKey(user: string | null, id: string) {
  return [user, `/api/deviations/${id}`, {}];
}

export function useDeviation(id: string) {
  const user = useCurrentUser();
  return useQuery({
    queryKey: devKey(user, id),
    queryFn: () => api<Deviation>(`/api/deviations/${id}`, { as: user ?? undefined }),
    enabled: !!user,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    retry: false,
  });
}

export function useSuggest(id: string, enabled: boolean) {
  const user = useCurrentUser();
  return useQuery({
    queryKey: [user, 'suggest', id],
    queryFn: () => api<Suggest>(`/api/deviations/${id}/suggest`, { as: user ?? undefined }),
    enabled: !!user && enabled,
  });
}

/** После мутации: карточку берём из ответа, остальное — перечитываем. */
function afterMutation(qc: QueryClient, user: string | null, dev: Deviation) {
  qc.setQueryData(devKey(user, dev.id), dev);
  qc.invalidateQueries({ predicate: (q) => !(q.queryKey[0] === user && q.queryKey[1] === `/api/deviations/${dev.id}`) });
}

export interface PatchBody {
  status?: string;
  action?: { text?: string; owner_login?: string | null; owner_node?: number | null; due_at?: string | null; playbook_ref?: string | null };
  hypothesis?: string;
  comment?: string;
}

export function usePatchDeviation(id: string) {
  const qc = useQueryClient();
  const user = useCurrentUser();
  return useMutation({
    mutationFn: (body: PatchBody) => api<Deviation>(`/api/deviations/${id}`, { method: 'PATCH', body, as: user ?? undefined }),
    onSuccess: (dev) => afterMutation(qc, user, dev),
  });
}

export function useRecheck(id: string) {
  const qc = useQueryClient();
  const user = useCurrentUser();
  return useMutation({
    mutationFn: () => api<RecheckResult>(`/api/admin/deviations/${id}/recheck`, { method: 'POST', as: user ?? undefined }),
    onSuccess: (r) => afterMutation(qc, user, r.deviation as Deviation),
  });
}

export function useDone(id: string) {
  const qc = useQueryClient();
  const user = useCurrentUser();
  return useMutation({
    mutationFn: (comment: string | null) => api<Deviation>(`/api/qc/deviations/${id}/done`, { method: 'POST', body: { comment }, as: user ?? undefined }),
    onSuccess: (dev) => afterMutation(qc, user, dev),
  });
}

/* ---------- «Что изменилось» ---------- */

export interface ChangesState {
  days: number;
  now: string;
  items: ChangeItem[];
  created: string[];
  ready: DevLite[];
  branches: string[];
}

let changes: ChangesState | null = null;
const listeners = new Set<() => void>();
function setChanges(v: ChangesState | null) {
  changes = v;
  listeners.forEach((f) => f());
}
export function closeChanges() {
  setChanges(null);
}
export function useChanges(): ChangesState | null {
  return useSyncExternalStore(
    (f) => {
      listeners.add(f);
      return () => listeners.delete(f);
    },
    () => changes,
  );
}

const BRANCH: Record<string, string> = { with_action: 'с решением', no_action: 'без решения' };

/** Перемотка со снимком Пульса до и после — для панели «Что изменилось». */
export function useAdvanceWithChanges() {
  const qc = useQueryClient();
  const user = useCurrentUser();
  const units = useUnits();
  return useMutation({
    mutationFn: async (days: number) => {
      const key = [user, 'overview', units];
      const loadOverview = () => api<Overview>('/api/overview', { query: { units }, as: user ?? undefined });
      const before = qc.getQueryData<Overview>(key) ?? (await loadOverview());
      const r = await api<Advance>('/api/demo/advance', { method: 'POST', query: { days }, as: user ?? undefined });
      const after = await loadOverview();
      const devs = await api<Portfolio>('/api/deviations', { as: user ?? undefined });
      return { r, before, after, devs, days };
    },
    onSuccess: ({ r, before, after, devs, days }) => {
      qc.setQueryData([user, 'overview', units], after);
      qc.invalidateQueries({ predicate: (q) => !(q.queryKey[0] === user && q.queryKey[1] === 'overview' && q.queryKey[2] === units) });
      setChanges({
        days,
        now: r.now,
        items: diffOverview(before as unknown as OverviewSnap, after as unknown as OverviewSnap),
        created: r.deviations_created,
        ready: readyForRecheck(devs.items as unknown as DevLite[], r.now, MIN_RECHECK_DAYS),
        branches: [...new Set(Object.values(r.branches ?? {}).map((b) => BRANCH[String(b)] ?? String(b)))],
      });
    },
  });
}
