// «Глазами другой роли»: текущий экран (с тем же URL) открывается в новой вкладке под другим пользователем (?as=).
import { Eye } from 'lucide-react';
import { useLocation } from 'react-router';
import { useMe, useUsers } from '../api/hooks';

export function EyesOfRole({ compact }: { compact?: boolean }) {
  const users = useUsers();
  const me = useMe();
  const location = useLocation();
  const open = (login: string) => {
    const sp = new URLSearchParams(location.search);
    sp.set('as', login);
    window.open(`${window.location.pathname}#${location.pathname}?${sp}`, '_blank', 'noopener');
  };
  return (
    <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      <Eye size={18} aria-hidden />
      {compact ? <span className="visually-hidden">Глазами другой роли</span> : <span>Глазами другой роли:</span>}
      <select
        value=""
        aria-label="Открыть этот экран глазами другого пользователя"
        style={{ height: 36, padding: '0 10px', border: '1px solid var(--border-strong)', borderRadius: 10, background: 'var(--surface)' }}
        onChange={(e) => {
          if (e.target.value) open(e.target.value);
          e.target.value = '';
        }}
      >
        <option value="">{compact ? 'Глазами другой роли…' : 'выбрать пользователя…'}</option>
        {(users.data ?? [])
          .filter((u) => u.login !== me.data?.login)
          .map((u) => (
            <option key={u.login} value={u.login}>
              {u.name}
            </option>
          ))}
      </select>
    </label>
  );
}
