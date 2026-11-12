import { useLayoutEffect, useRef, useState } from 'react';

/** Ширина контейнера в пикселях (для SVG без растяжения). */
export function useWidth<T extends HTMLElement>(fallback = 240) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => setWidth(Math.max(40, Math.round(el.getBoundingClientRect().width)));
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}
