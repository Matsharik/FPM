// Пользователь хранится на вкладку (sessionStorage), последний выбранный — в localStorage
// как значение по умолчанию. ?as=<login> открывает вкладку под другим пользователем
// («Глазами другой роли»): свой логин запоминается в `fpm.self`.

const TAB_KEY = 'fpm.user';
const SELF_KEY = 'fpm.self';
const LAST_KEY = 'fpm.lastUser';

type Listener = () => void;
const listeners = new Set<Listener>();

function read(storage: Storage | undefined, key: string): string | null {
  try {
    return storage?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

function write(storage: Storage | undefined, key: string, value: string | null): void {
  try {
    if (value === null) storage?.removeItem(key);
    else storage?.setItem(key, value);
  } catch {
    /* приватный режим: живём без хранилища */
  }
}

const ss = typeof window !== 'undefined' ? window.sessionStorage : undefined;
const ls = typeof window !== 'undefined' ? window.localStorage : undefined;

let memoryUser: string | null = null;

export function getUser(): string | null {
  return read(ss, TAB_KEY) ?? memoryUser ?? read(ls, LAST_KEY);
}

/** Свой логин, если вкладка открыта «глазами» другого пользователя. */
export function getSelf(): string | null {
  return read(ss, SELF_KEY);
}

export function isViewingAs(): boolean {
  const self = getSelf();
  return !!self && self !== getUser();
}

function emit() {
  for (const fn of listeners) fn();
}

/** Обычный вход: пользователь вкладки и значение по умолчанию для новых вкладок. */
export function setUser(login: string): void {
  memoryUser = login;
  write(ss, TAB_KEY, login);
  write(ss, SELF_KEY, null);
  write(ls, LAST_KEY, login);
  emit();
}

/** Вкладка «глазами» другого пользователя: свой логин не теряется. */
export function enterAs(login: string): void {
  const current = getSelf() ?? getUser();
  if (current && current !== login) write(ss, SELF_KEY, current);
  memoryUser = login;
  write(ss, TAB_KEY, login);
  emit();
}

export function returnToSelf(): string | null {
  const self = getSelf();
  if (self) {
    memoryUser = self;
    write(ss, TAB_KEY, self);
  }
  write(ss, SELF_KEY, null);
  emit();
  return self;
}

export function clearUser(): void {
  memoryUser = null;
  write(ss, TAB_KEY, null);
  write(ss, SELF_KEY, null);
  write(ls, LAST_KEY, null);
  emit();
}

export function subscribeUser(fn: Listener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
