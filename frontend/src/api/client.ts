// HTTP-клиент: абсолютный URL к бэкенду (slovesny.ru/api-mvp), X-User на каждый запрос (кроме входа и /health),
// единый разбор ошибок {"error": {"code", "message", "details"}}.
import { getUser } from '../session/user';

// Базовый URL вашего бэкенда на VPS
const API_BASE_URL = 'https://slovesny.ru/api-mvp';

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }

  get isNotFound(): boolean {
    return this.status === 404 || this.code.endsWith('_not_found');
  }
}

/** Сервер не ответил (не запущен, сеть). */
export class NetworkError extends Error {
  constructor(message = 'Сервер не отвечает') {
    super(message);
    this.name = 'NetworkError';
  }
}

const PUBLIC_PATHS = new Set(['/api/auth/users', '/health']);

type Query = Record<string, string | number | boolean | null | undefined>;

export function buildUrl(path: string, query?: Query): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === undefined || value === null || value === '') continue;
    params.set(key, String(value));
  }
  
  // ИСПРАВЛЕНО ТУТ: Приклеиваем базовый URL к пути
  const fullPath = `${API_BASE_URL}${path}`;
  
  const qs = params.toString();
  return qs ? `${fullPath}?${qs}` : fullPath;
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  query?: Query;
  body?: unknown;
  /** Логин вместо текущего (матрица прав на входе). */
  as?: string;
  signal?: AbortSignal;
}

export async function api<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  const user = opts.as ?? getUser();
  
  // Если путь не публичный и есть пользователь — добавляем заголовок X-User
  if (!PUBLIC_PATHS.has(path) && user) headers['X-User'] = user;
  
  let body: BodyInit | undefined;
  if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json; charset=utf-8';
    body = JSON.stringify(opts.body);
  }
  
  let res: Response;
  try {
    res = await fetch(buildUrl(path, opts.query), {
      method: opts.method ?? 'GET',
      headers,
      body,
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err;
    throw new NetworkError();
  }
  
  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  
  if (!res.ok) {
    const e = (data as { error?: { code?: string; message?: string; details?: Record<string, unknown> } } | null)?.error;
    if (!e && res.status >= 500) throw new NetworkError(`Сервер вернул ошибку ${res.status}`);
    throw new ApiError(res.status, e?.code ?? `http_${res.status}`, e?.message ?? `Ошибка ${res.status}`, e?.details ?? {});
  }
  
  return data as T;
}