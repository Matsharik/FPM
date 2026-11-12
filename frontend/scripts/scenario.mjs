// Демо-сценарий «Брак» (раздел 8, шаги 1–10) кликами в браузере + скриншоты в docs/screens/.
// Нужен бэкенд с собранным web/: python run.py --port 8790 --data <папка>. Сценарий сам сбрасывает стенд.
// Запуск: npm run scenario
import { chromium, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const BASE = process.env.FPM_URL ?? 'http://127.0.0.1:8790/';
const OUT = new URL('../../docs/screens/', import.meta.url);
const shot = (page, name) => page.screenshot({ path: fileURLToPath(new URL(`${name}.png`, OUT)) });

await mkdir(OUT, { recursive: true });
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
const step = (n, text) => console.log(`шаг ${n}: ${text}`);

// 1. Директор → сброс стенда
await fetch(BASE + 'api/demo/reset', { method: 'POST', headers: { 'X-User': 'director' } });
await page.goto(BASE + '#/login');
await page.evaluate(() => {
  sessionStorage.clear();
  localStorage.setItem('fpm.lastUser', 'director');
});
await page.getByRole('button', { name: /Генеральный директор/ }).first().click();
step(1, 'вход директора, стенд сброшен');

// 2. Пульс
await expect(page.getByText('Критично: Качество')).toBeVisible();
step(2, 'Пульс: Качество критично, Команда — внимание');

// 3. Карточка
await page.getByRole('link', { name: 'Открыть карточку DEV-0001' }).click();
await expect(page.getByRole('heading', { name: /Доля обращений по браку · Поддержка/ })).toBeVisible();
await expect(page.getByText(/при пороге «критично» 8/)).toBeVisible();
await page.waitForTimeout(600);
await shot(page, 'card-1-signal');
step(3, 'карточка: сигнал 9 % при пороге 8 %');

// 4. Контекст
await page.locator('#context').scrollIntoViewIfNeeded();
await expect(page.getByText('Линейка: Выпускные альбомы')).toBeVisible();
await page.waitForTimeout(300);
await shot(page, 'card-2-context');
step(4, 'контекст: сегмент, затронутые заказы, на что влияет');

// 5. Причина → дерево
await page.getByRole('link', { name: 'Открыть в дереве' }).click();
await expect(page.getByText('Путь к первопричине')).toBeVisible();
await page.waitForTimeout(900);
await shot(page, 'tree-trace');
// Узлы и вкладки дерева кликабельны: клик по «Сборке» открывает инспектор узла, клик по вкладке — инспектор KPI.
await page.getByRole('button', { name: /^Сборка:/ }).click();
await expect(page).toHaveURL(/panel=node(:|%3A)11/);
await page.getByRole('tab', { name: /Доля брака/ }).first().click();
await expect(page).toHaveURL(/panel=kpi(:|%3A)11(:|%3A)defect_rate/);
await expect(page.getByLabel('Инспектор')).toBeVisible();
step(5, 'расследование в дереве; клик по узлу и вкладке открывает инспектор');
await page.getByRole('link', { name: 'Назад в карточку' }).click();

// 6. Действие
await page.locator('#action').scrollIntoViewIfNeeded();
await page.getByRole('button', { name: 'Применить' }).first().click();
await expect(page.locator('#act-owner')).toHaveValue('head_prod');
await page.getByRole('button', { name: 'Назначить действие' }).click();
await expect(page.getByText('Решение сохранено и записано в журнал')).toBeVisible();
await page.waitForTimeout(800);
await page.locator('#action').scrollIntoViewIfNeeded();
await shot(page, 'card-3-action');
step(6, 'действие назначено');

// 7. Перепроверка рано → перемотка
await page.locator('#check').scrollIntoViewIfNeeded();
await page.getByRole('button', { name: 'Перепроверить' }).click();
await expect(page.getByText(/Рано проверять: прошло 0 из 3 суток/)).toBeVisible();
await shot(page, 'card-4-pending');
await page.getByRole('button', { name: 'Перемотать демо-время на 7 дней' }).click();
await expect(page.getByLabel('Что изменилось')).toBeVisible({ timeout: 20000 });
await page.waitForTimeout(500);
await shot(page, 'changes-after-advance');
step(7, 'pending → перемотка → «Что изменилось»');

// 8. Перепроверка → проверено
await page.locator('#check').scrollIntoViewIfNeeded();
await page.getByRole('button', { name: 'Перепроверить' }).click();
await expect(page.getByText(/Решение сработало: 7,78/)).toBeVisible();
await page.waitForTimeout(600);
await page.locator('#check').scrollIntoViewIfNeeded();
await shot(page, 'card-5-verified');
step(8, 'проверено: 7,78 % → 4,44 %');

// 9. Пульс и решения
await page.getByRole('link', { name: 'Пульс' }).click();
await expect(page.getByText('100 %')).toBeVisible();
await page.waitForTimeout(500);
await shot(page, 'pulse-after-decision');
await page.getByRole('link', { name: 'Решения' }).first().click();
await expect(page.getByRole('heading', { name: 'Проверено' })).toBeVisible();
await shot(page, 'portfolio-after');
step(9, 'Пульс и Решения: 1 проверено, 100 %');

// 10. Глазами head_client (новая вкладка с ?as=)
const tab = await ctx.newPage();
await tab.goto(BASE + '#/deviations/DEV-0001?as=head_client');
await expect(tab.getByText('Вы смотрите как')).toBeVisible();
await expect(tab.getByText(/Причина в смежном подразделении: Сборка/)).toBeVisible();
await tab.locator('#cause').scrollIntoViewIfNeeded();
await tab.waitForTimeout(400);
await shot(tab, 'card-head_client-cause');
step(10, '«Глазами» head_client: причина в смежном подразделении');

console.log(errors.length ? `ошибки консоли: ${errors.join(' | ')}` : 'ошибок консоли нет');
await browser.close();
