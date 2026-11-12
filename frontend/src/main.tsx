import '@fontsource-variable/inter';
import './styles/global.css';
import { QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { Navigate, RouterProvider, createHashRouter } from 'react-router';
import { makeQueryClient } from './api/hooks';
import { PRODUCT_SHORT } from './brand';
import { Home } from './screens/Home';
import { Login } from './screens/login/Login';
import { Pulse } from './screens/pulse/Pulse';
import { Stub } from './screens/Stub';
import { TreeScreen } from './screens/tree/Tree';
import { DeviationCard } from './screens/deviation/DeviationCard';
import { Portfolio } from './screens/deviations/Portfolio';
import { UiKit } from './screens/uikit/UiKit';
import { clearUser, enterAs, getUser } from './session/user';
import { Shell } from './shell/Shell';
import { Toaster } from './ui/Toast';

document.title = PRODUCT_SHORT;

// ?as=<login> обрабатываем до первого запроса, чтобы вкладка сразу пошла под нужным логином.
const asParam = new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('as');
if (asParam && asParam !== getUser()) enterAs(asParam);

const router = createHashRouter([
  { path: '/login', element: <Login /> },
  {
    path: '/',
    element: <Shell />,
    children: [
      { index: true, element: <Home /> },
      { path: 'pulse', element: <Pulse /> },
      { path: 'tree', element: <TreeScreen /> },
      { path: 'deviations', element: <Portfolio /> },
      { path: 'deviations/:id', element: <DeviationCard /> },
      { path: 'orders', element: <Stub /> },
      { path: 'team', element: <Stub /> },
      { path: 'queue', element: <Stub /> },
      { path: 'sources', element: <Stub /> },
      { path: 'glossary/:metric?', element: <Stub /> },
      { path: 'audit', element: <Stub /> },
      { path: 'ui', element: <UiKit /> },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
]);

// 401 unauthorized / unknown_user: сбросить пользователя и вернуться ко входу с пояснением.
const queryClient = makeQueryClient((code) => {
  clearUser();
  queryClient.clear();
  router.navigate(`/login?reason=${code}`);
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
      <Toaster />
    </QueryClientProvider>
  </StrictMode>,
);
