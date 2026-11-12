// Узел дерева (наброски): белая карточка + лента KPI-вкладок снизу, как вкладки браузера.
// Вкладка — порт: из неё выходят связи. Верхняя полоса вкладки — цвет статуса KPI.
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react';
import { ChevronDown, ChevronRight, CircleAlert, Lock, User, Users, Building2, Briefcase, Boxes } from 'lucide-react';
import { memo } from 'react';
import type { GNode } from '../../lib/graph';
import { abbrev } from '../../lib/graph';
import { fmtNum } from '../../lib/format';
import { KPI_STATUS, asKpiStatus } from '../../lib/status';
import { NODE_TYPE } from '../../inspector/NodePanel';
import { Tooltip } from '../../ui/Floating';
import { toneOf } from '../../ui/Status';
import { nodeSize } from './layout';
import s from './tree.module.css';

export type NodeRole = 'none' | 'dim' | 'path' | 'root' | 'alt' | 'impact-source' | 'impact-hit';

export interface OrgNodeData extends Record<string, unknown> {
  node: GNode;
  expandedKpi: string | null;
  selected: boolean;
  role: NodeRole;
  hidden: number;
  collapsed: boolean;
  hasChildren: boolean;
  devIds: string[];
  pathKpis: string[];
  onSelect: (id: number) => void;
  onTab: (id: number, kpi: string) => void;
  onToggle: (id: number) => void;
  onOpenHidden: (id: number) => void;
  onDev: (id: string) => void;
}

export type OrgNodeT = Node<OrgNodeData, 'org'>;

const TYPE_ICON: Record<string, typeof User> = {
  system: Building2,
  function: Briefcase,
  department: Boxes,
  team: Users,
  person: User,
};

function OrgNodeImpl({ data }: NodeProps<OrgNodeT>) {
  const { node: n, expandedKpi, selected, role, hidden, collapsed, hasChildren, devIds } = data;
  const boundary = !n.clickable;
  const Icon = boundary ? Lock : TYPE_ICON[n.type] ?? Boxes;
  const size = nodeSize(n);
  const deep = n.deep_status && n.deep_status !== n.status && (n.deep_status === 'red' || n.deep_status === 'yellow');
  const status = n.status ?? null;
  const cls = [
    s.node,
    boundary ? s.nodeBoundary : '',
    selected ? s.nodeSelected : '',
    role === 'dim' ? s.nodeDim : '',
    role === 'path' || role === 'alt' ? s.nodePath : '',
    role === 'root' ? s.nodeRoot : '',
    role === 'impact-source' || role === 'impact-hit' ? s.nodeImpact : '',
  ].join(' ');

  const card = (
    <div
      className={s.card}
      role={boundary ? undefined : 'button'}
      tabIndex={boundary ? -1 : 0}
      aria-label={boundary ? `${n.name}: вне вашей зоны` : `${n.name}: ${KPI_STATUS[asKpiStatus(status)].label}`}
      onClick={() => !boundary && data.onSelect(n.id)}
      onKeyDown={(e) => {
        if (!boundary && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          data.onSelect(n.id);
        }
      }}
    >
      <div className={s.cardTop}>
        <span className={s.typeIcon} aria-hidden>
          <Icon size={14} />
        </span>
        <span className={s.name} title={n.name}>
          {n.name}
        </span>
        {status ? <span className={`${s.statusDot} ${s[`dot-${toneOf(status)}`]}`} title={KPI_STATUS[asKpiStatus(status)].label} /> : null}
        {deep ? <span className={`${s.deepDot} ${s[`dot-${toneOf(n.deep_status)}`]}`} title="Внутри ветки есть проблема" /> : null}
      </div>
      <div className={s.cardMeta}>
        <span className={s.owner}>{boundary ? `вне зоны · ${n.owner}` : `${NODE_TYPE[n.type] ?? n.type} · ${n.owner}`}</span>
        {hidden > 0 ? (
          <button
            type="button"
            className={s.hiddenPill}
            title="Показать скрытые узлы ветки"
            onClick={(e) => {
              e.stopPropagation();
              data.onOpenHidden(n.id);
            }}
          >
            +{hidden} {collapsed ? '' : 'в норме'}
          </button>
        ) : null}
      </div>
      {devIds.length ? (
        <button
          type="button"
          className={s.devBadge}
          onClick={(e) => {
            e.stopPropagation();
            data.onDev(devIds[0]);
          }}
        >
          <CircleAlert size={12} aria-hidden />
          {devIds[0]}
        </button>
      ) : null}
      {hasChildren && !boundary ? (
        <button
          type="button"
          className={s.chevron}
          aria-label={collapsed ? 'Развернуть ветку' : 'Свернуть ветку'}
          onClick={(e) => {
            e.stopPropagation();
            data.onToggle(n.id);
          }}
        >
          {collapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
        </button>
      ) : null}
    </div>
  );

  return (
    <div className={cls} style={{ width: size.width }}>
      <Handle type="target" position={Position.Top} id="in" className={s.handle} isConnectable={false} />
      {boundary ? <Tooltip content={`Вне вашей зоны. Владелец: ${n.owner}`}>{card}</Tooltip> : card}
      {n.kpis.length ? (
        <div className={s.tabs} role="tablist" aria-label={`Показатели узла ${n.name}`}>
          {n.kpis.map((k) => {
            const open = k.name === expandedKpi;
            const tone = toneOf(k.status);
            const onPath = data.pathKpis.includes(k.name);
            const tab = (
              <div
                key={k.name}
                role="tab"
                aria-selected={open}
                tabIndex={boundary ? -1 : 0}
                className={`${s.tab} ${open ? s.tabOpen : ''} ${onPath ? s.tabPath : ''} ${boundary ? s.tabBoundary : ''}`}
                style={{ borderTopColor: `var(--${tone === 'unknown' ? 'unknown' : tone})` }}
                onClick={(e) => {
                  e.stopPropagation();
                  if (!boundary) data.onTab(n.id, k.name);
                }}
                onKeyDown={(e) => {
                  if (!boundary && (e.key === 'Enter' || e.key === ' ')) {
                    e.preventDefault();
                    data.onTab(n.id, k.name);
                  }
                }}
              >
                {open ? (
                  <>
                    <span className={s.tabTitle}>{k.title}</span>
                    <span className={s.tabValue}>
                      {boundary || k.value === null || k.value === undefined ? (
                        <span className={s.tabStatus}>{KPI_STATUS[asKpiStatus(k.status)].label}</span>
                      ) : (
                        <>
                          {fmtNum(k.value)}
                          {k.unit ? <span className={s.tabUnit}>&nbsp;{k.unit}</span> : null}
                        </>
                      )}
                    </span>
                  </>
                ) : (
                  <span className={s.tabCode}>{abbrev(k.title)}</span>
                )}
                <Handle type="source" position={Position.Bottom} id={`k:${k.name}`} className={s.handle} isConnectable={false} />
              </div>
            );
            return open ? (
              tab
            ) : (
              <Tooltip key={k.name} content={`${k.title}: ${KPI_STATUS[asKpiStatus(k.status)].label}${!boundary && k.value !== null && k.value !== undefined ? ` · ${fmtNum(k.value)} ${k.unit ?? ''}` : ''}`}>
                {tab}
              </Tooltip>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

export const OrgNode = memo(OrgNodeImpl);
