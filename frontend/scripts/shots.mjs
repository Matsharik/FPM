// Скриншоты ключевых экранов в docs/screens/ (Playwright, Chromium).
// Нужен бэкенд с собранным web/: python run.py --reset --port 8790 --data <папка>
// Запуск: npm run shots [-- фильтр]   (фильтр — часть имени скриншота)
import { chromium } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const BASE = process.env.FPM_URL ?? 'http://127.0.0.1:8790/';
const OUT = new URL('../../docs/screens/', import.meta.url);
const filter = process.argv[2] ?? '';

const SIZES = { '1920': { width: 1920, height: 1080 }, '1366': { width: 1366, height: 768 } };

// [имя, пользователь (null — без входа), маршрут, размеры]
const SHOTS = [
  ['login', null, '/login', ['1920', '1366']],
  ['pulse-director', 'director', '/pulse', ['1920', '1366']],
  ['pulse-head_client', 'head_client', '/pulse', ['1920']],
  ['pulse-head_prod', 'head_prod', '/pulse', ['1920']],
  ['pulse-qc_otk', 'qc_otk', '/pulse', ['1920', '1366']],
  ['ui-kit', 'director', '/ui', ['1920']],
  ['tree-director', 'director', '/tree', ['1920', '1366']],
  ['tree-director-all', 'director', '/tree?only=all', ['1920']],
  ['tree-inspector-sborka', 'director', '/tree?focus=11&kpi=defect_rate&panel=kpi:11:defect_rate&forecast=14', ['1920', '1366']],
  ['tree-node-podderzhka', 'director', '/tree?focus=5&panel=node:5', ['1920']],
  ['tree-impact-sborka', 'director', '/tree?focus=11&impact=11:defect_rate', ['1920']],
  ['tree-head_prod', 'head_prod', '/tree', ['1920']],
  ['tree-head_client', 'head_client', '/tree', ['1920']],
  ['tree-as-head_client', 'director', '/tree?as=head_client', ['1366']],
  ['card-dev0001', 'director', '/deviations/DEV-0001', ['1920', '1366']],
];

await mkdir(OUT, { recursive: true });
const browser = await chromium.launch();
let failed = 0;
for (const [name, user, route, sizes] of SHOTS) {
  if (filter && !name.includes(filter)) continue;
  for (const size of sizes) {
    const page = await browser.newPage({ viewport: SIZES[size], deviceScaleFactor: 1 });
    const errors = [];
    page.on('pageerror', (e) => errors.push(e.message));
    page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
    await page.goto(BASE + '#/login');
    await page.evaluate((u) => {
      sessionStorage.clear();
      if (u) {
        sessionStorage.setItem('fpm.user', u);
        localStorage.setItem('fpm.lastUser', u);
      } else {
        localStorage.removeItem('fpm.lastUser');
      }
    }, user);
    await page.goto(BASE + '#' + route);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(400);
    const file = fileURLToPath(new URL(`${name}-${size}.png`, OUT));
    await page.screenshot({ path: file, fullPage: name === 'ui-kit' });
    console.log(errors.length ? 'WARN' : 'ok  ', `${name}-${size}.png`, errors.join(' | '));
    if (errors.length) failed++;
    await page.close();
  }
}
await browser.close();
if (failed) process.exitCode = 1;
