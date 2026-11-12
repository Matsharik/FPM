// Связь дерева: вес (или доля вклада) по-русски на подписи; межфункциональная — со значком «влияние».
import { BaseEdge, EdgeLabelRenderer, getBezierPath, type Edge, type EdgeProps } from '@xyflow/react';
import { Zap } from 'lucide-react';
import { memo } from 'react';
import { Tooltip } from '../../ui/Floating';
import s from './tree.module.css';

export type EdgeTone = 'active' | 'muted' | 'boundary' | 'path' | 'alt' | 'impact' | 'dim';

export interface WeightEdgeData extends Record<string, unknown> {
  tone: EdgeTone;
  label: string | null;
  cross: boolean;
  tooltip: string;
  onOpen: () => void;
}

export type WeightEdgeT = Edge<WeightEdgeData, 'weight'>;

const STYLE: Record<EdgeTone, React.CSSProperties> = {
  active: { stroke: 'var(--text)', strokeWidth: 2 },
  muted: { stroke: 'var(--text-muted)', strokeWidth: 1.25, strokeDasharray: '4 4', opacity: 0.35 },
  boundary: { stroke: 'var(--unknown)', strokeWidth: 1.5 },
  path: { stroke: 'var(--crit)', strokeWidth: 4 },
  alt: { stroke: 'var(--text)', strokeWidth: 1.25, opacity: 0.8 },
  impact: { stroke: 'var(--impact)', strokeWidth: 3 },
  dim: { stroke: 'var(--border-strong)', strokeWidth: 1, opacity: 0.25 },
};

function WeightEdgeImpl({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data }: EdgeProps<WeightEdgeT>) {
  const [path, lx, ly] = getBezierPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, curvature: 0.35 });
  const tone = data?.tone ?? 'muted';
  const showLabel = !!data?.label && tone !== 'muted' && tone !== 'dim';
  return (
    <>
      <BaseEdge id={id} path={path} style={STYLE[tone]} interactionWidth={14} />
      {showLabel || (data?.cross && tone !== 'dim' && tone !== 'muted') ? (
        <EdgeLabelRenderer>
          <div className={`${s.edgeLabelWrap} nodrag nopan`} style={{ transform: `translate(-50%, -50%) translate(${lx}px, ${ly}px)` }}>
            <Tooltip content={data?.tooltip}>
              <button type="button" className={`${s.edgeLabel} ${s[`edge-${tone}`] ?? ''}`} onClick={data?.onOpen}>
                {data?.cross ? <Zap size={11} aria-label="межфункциональная связь" /> : null}
                {showLabel ? data?.label : null}
              </button>
            </Tooltip>
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}

export const WeightEdge = memo(WeightEdgeImpl);
