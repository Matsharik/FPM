// Временная заглушка экрана, который появится в следующих фазах. Данных не запрашивает.
import { Construction } from 'lucide-react';
import { useLocation, useParams } from 'react-router';
import { Page, ROUTE_TITLES } from '../shell/Shell';
import { EmptyState } from '../ui/States';

const PHASE: Record<string, string> = {
  tree: 'Ф2',
  deviations: 'Ф3',
  orders: 'Ф4',
  sources: 'Ф4',
  team: 'Ф5',
  queue: 'Ф5',
  glossary: 'Ф5',
  audit: 'Ф5',
};

export function Stub() {
  const location = useLocation();
  const params = useParams();
  const root = location.pathname.split('/').filter(Boolean)[0] ?? '';
  const title = ROUTE_TITLES[root] ?? root;
  const id = params.id ? ` ${params.id}` : '';
  return (
    <Page>
      <h1 style={{ marginBottom: 24 }}>
        {title}
        {id}
      </h1>
      <EmptyState
        icon={<Construction size={20} />}
        title="Экран в работе"
        text={`Этот экран собирается в фазе ${PHASE[root] ?? 'следующей'}. Переход сюда уже работает: адрес и параметры сохранятся.`}
      />
    </Page>
  );
}
