// Снимает фикстуры для страницы #/ui и тестов настоящими запросами к бэкенду.
// Нужен сервер после сброса: python run.py --reset --port 8790 --data <папка>
// Фикстуры НЕ используются как запасной источник данных в рантайме.
import { mkdir, writeFile } from 'node:fs/promises';

const BASE = process.env.FPM_API ?? 'http://127.0.0.1:8790';
const OUT = new URL('../src/fixtures/', import.meta.url);

async function get(path, user) {
  const res = await fetch(BASE + path, { headers: user ? { 'X-User': user } : {} });
  if (!res.ok) throw new Error(`${path} от ${user}: ${res.status} ${await res.text()}`);
  return res.json();
}

const USERS = ['director', 'head_client', 'head_prod', 'qc_otk', 'builder'];
const jobs = {
  'users': () => get('/api/auth/users'),
  'clock': () => get('/api/demo/clock', 'director'),
  'graph.director': () => get('/api/graph', 'director'),
  'graph.head_prod': () => get('/api/graph', 'head_prod'),
  'series.11.defect_rate': () => get('/api/kpi/11/defect_rate?from=2026-11-09T00%3A00%3A00%2B03%3A00&agg=day', 'director'),
  'series.5.defect_tickets_share': () =>
    get('/api/kpi/5/defect_tickets_share?from=2026-11-09T00%3A00%3A00%2B03%3A00&agg=day', 'director'),
  'forecast.5.defect_tickets_share': () => get('/api/kpi/5/defect_tickets_share/forecast?horizon=14', 'director'),
  'deviation.DEV-0001.director': () => get('/api/deviations/DEV-0001', 'director'),
};
for (const u of USERS) {
  jobs[`me.${u}`] = () => get('/api/me', u);
  jobs[`overview.${u}`] = () => get('/api/overview', u);
}

await mkdir(OUT, { recursive: true });
for (const [name, job] of Object.entries(jobs)) {
  const data = await job();
  await writeFile(new URL(`${name}.json`, OUT), JSON.stringify(data, null, 2) + '\n', 'utf8');
  console.log('ok', name);
}
