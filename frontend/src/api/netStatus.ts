// Признак «сервер не отвечает» для баннера на любом экране.
import { useSyncExternalStore } from 'react';

let down = false;
const listeners = new Set<() => void>();

export function setNetworkDown(v: boolean): void {
  if (down === v) return;
  down = v;
  listeners.forEach((fn) => fn());
}

export function useNetworkDown(): boolean {
  return useSyncExternalStore(
    (fn) => {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    () => down,
  );
}
