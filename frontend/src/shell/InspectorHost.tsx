// Один инспектор на всех экранах: содержимое берётся из panel= в URL.
// «←» — шаг назад по истории, «×» — убрать panel=.
import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import { useSetParams } from '../app/nav';
import { NodePanel, type ShellChrome } from '../inspector/NodePanel';
import { EventPanel, LinkPanel } from '../inspector/OtherPanels';
import { parsePanel } from '../lib/panel';
import { InspectorShell, readInspectorWidth, saveInspectorWidth } from '../ui/Inspector';
import { EmptyState } from '../ui/States';
import s from './shell.module.css';

export function InspectorHost() {
  const [sp] = useSearchParams();
  const navigate = useNavigate();
  const setParams = useSetParams();
  const [width, setWidth] = useState(readInspectorWidth);
  const panel = parsePanel(sp.get('panel'));
  if (!panel) return null;
  const chrome: ShellChrome = {
    onBack: () => navigate(-1),
    onClose: () => setParams({ panel: null }),
    onResize: (w) => {
      setWidth(w);
      saveInspectorWidth(w);
    },
  };
  let body;
  switch (panel.kind) {
    case 'node':
      body = <NodePanel key={`n${panel.nodeId}`} nodeId={panel.nodeId} kpi={null} chrome={chrome} />;
      break;
    case 'kpi':
      body = <NodePanel key={`n${panel.nodeId}`} nodeId={panel.nodeId} kpi={panel.kpi} chrome={chrome} />;
      break;
    case 'link':
      body = <LinkPanel linkId={panel.linkId} chrome={chrome} />;
      break;
    case 'event':
      body = <EventPanel eventId={panel.eventId} chrome={chrome} />;
      break;
    default:
      body = (
        <InspectorShell kicker="Заказ" title={panel.orderId} {...chrome}>
          <EmptyState title="Карточка заказа — в Ф4" text="Восемь этапов по четыре поля появятся вместе с экраном «Заказы»." />
        </InspectorShell>
      );
  }
  return (
    <div className={s.inspectorSlot} style={{ width }}>
      {body}
    </div>
  );
}
