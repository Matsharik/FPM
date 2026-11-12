// Бренд: полное название — в верхней панели и на входе; FPM — в мелких местах и во вкладке браузера.
export const PRODUCT_NAME = 'Фотопринт Manage';
export const PRODUCT_SHORT = 'FPM';
export const PRODUCT_TAGLINE = 'От сигнала к решению, которое можно проверить';

/** Логотип: жёлтый скруглённый квадрат с простым чёрным знаком «F» и точкой-сигналом. */
export function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden focusable="false">
      <rect width="32" height="32" rx="8" fill="#FFE600" />
      <path d="M9 23V9h10M9 16h8" stroke="#0A0A0A" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      <circle cx="22.5" cy="21.5" r="2.6" fill="#0A0A0A" />
    </svg>
  );
}
