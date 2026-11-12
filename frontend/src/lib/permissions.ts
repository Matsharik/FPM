// Права → интерфейс (раздел 2.3). Кнопки показываются только по /api/me → permissions.
import type { Permission } from '../api/types';

export const PERMISSIONS: Array<{ key: Permission; label: string; opens: string }> = [
  { key: 'demo.control', label: 'Управлять демо-временем', opens: 'перемотка и сброс демо-времени' },
  { key: 'deviations.manage', label: 'Назначать действия и менять статус решений', opens: 'назначить действие, сменить статус, гипотеза' },
  { key: 'deviations.recheck', label: 'Запускать перепроверку', opens: '«Перепроверить»' },
  { key: 'deviations.done', label: 'Отмечать действие выполненным', opens: '«Отметить выполненным»' },
  { key: 'flags.write', label: 'Ставить отметки на графиках', opens: 'отметки на графиках, флажок решения' },
  { key: 'people.read', label: 'Видеть сотрудников и их показатели', opens: 'экран «Команда», люди в инспекторе' },
  { key: 'points.write', label: 'Вносить значения показателей', opens: '«Внести значение»' },
  { key: 'structure.write', label: 'Менять структуру: узлы, KPI, связи', opens: 'режим конструктора' },
  { key: 'glossary.write', label: 'Править словарь метрик', opens: 'правка словаря' },
  { key: 'config.io', label: 'Импорт и экспорт конфигурации', opens: 'экспорт и импорт' },
];

/** Уровень управления (ТЗ, слайд 5). */
export function levelLabel(role: string, seesEverything?: boolean | null): string {
  if (role === 'admin') return seesEverything ? 'Руководство' : 'Руководитель функции';
  if (role === 'qc') return 'Операционная команда';
  if (role === 'builder') return 'Методолог (конструктор)';
  return role;
}

export function can(perms: readonly string[] | undefined, p: Permission): boolean {
  return !!perms && perms.includes(p);
}
