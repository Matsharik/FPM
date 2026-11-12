// «?» у названия KPI: карточка словаря (определение, формула, источник, пороги).
import { CircleHelp } from 'lucide-react';
import { Link } from 'react-router';
import { useGlossary } from '../api/hooks';
import { useLinkTo } from '../app/nav';
import { fmtNum } from '../lib/format';
import { Popover } from './Floating';
import s from './ui.module.css';

const DIRECTION: Record<string, string> = { lower_better: 'чем меньше, тем лучше', higher_better: 'чем больше, тем лучше' };

export function GlossaryHint({ metric }: { metric: string | null | undefined }) {
  const glossary = useGlossary();
  const linkTo = useLinkTo();
  if (!metric) return null;
  const m = glossary.data?.metrics?.[metric];
  return (
    <Popover
      trigger={
        <button type="button" className={s.hint} aria-label="Определение показателя">
          <CircleHelp size={15} />
        </button>
      }
    >
      {m ? (
        <>
          <div className={s.popTitle}>{m.title}</div>
          <dl className={s.provList}>
            {m.definition ? (
              <>
                <dt>Определение</dt>
                <dd>{m.definition}</dd>
              </>
            ) : null}
            {m.formula ? (
              <>
                <dt>Формула</dt>
                <dd>{m.formula}</dd>
              </>
            ) : null}
            <dt>Единица</dt>
            <dd>{m.unit}</dd>
            <dt>Направление</dt>
            <dd>{DIRECTION[m.direction] ?? m.direction}</dd>
            <dt>Владелец</dt>
            <dd>{m.owner}</dd>
            {Object.entries(m.thresholds ?? {}).map(([profile, t]) => {
              const th = t as { target?: number; warn?: number; crit?: number };
              return (
                <span key={profile} style={{ display: 'contents' }}>
                  <dt>Пороги ({profile === 'season' ? 'сезон' : 'обычные'})</dt>
                  <dd>
                    цель {fmtNum(th.target)} · внимание {fmtNum(th.warn)} · критично {fmtNum(th.crit)}
                  </dd>
                </span>
              );
            })}
          </dl>
          <div style={{ marginTop: 12 }}>
            <Link to={linkTo(`/glossary/${metric}`)}>Открыть в словаре</Link>
          </div>
        </>
      ) : (
        <span className="muted">{glossary.isPending ? 'Загружаю словарь…' : 'Метрики нет в словаре'}</span>
      )}
    </Popover>
  );
}
