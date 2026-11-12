// Домашний экран по роли из /api/me.
import { Navigate } from 'react-router';
import { useMe } from '../api/hooks';
import { useLinkTo } from '../app/nav';
import { Page, homeFor } from '../shell/Shell';
import { ErrorState, Skeleton } from '../ui/States';

export function Home() {
  const me = useMe();
  const linkTo = useLinkTo();
  if (me.data) return <Navigate to={linkTo(homeFor(me.data))} replace />;
  return <Page>{me.isError ? <ErrorState error={me.error} onRetry={() => me.refetch()} /> : <Skeleton height={34} width={320} />}</Page>;
}
