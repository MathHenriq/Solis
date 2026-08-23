import { lazy, type ComponentType, type LazyExoticComponent } from "react";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { AppShell } from "./components/shell/AppShell";
import { NAV_ITEMS } from "./lib/nav-items";

/* Só existe em desenvolvimento. A condição fica AQUI, e não só na rota, porque
 * um `lazy(() => import(...))` no topo do módulo faz o bundler emitir o chunk
 * mesmo que a rota nunca seja registrada — peso morto no build de produção. */
const AssinaturaPreview = import.meta.env.DEV
  ? lazy(() => import("./views/_AssinaturaPreview"))
  : null;

/* Uma view lazy por rota. O import dinâmico é literal de propósito: o Vite
 * precisa ver o caminho pra gerar o chunk, então isto não pode virar um
 * template string montado a partir de NAV_ITEMS. */
const VIEWS: Record<string, LazyExoticComponent<ComponentType>> = {
  conversa: lazy(() => import("./views/Conversa")),
  memoria: lazy(() => import("./views/Memoria")),
  "modelos-locais": lazy(() => import("./views/ModelosLocais")),
  ferramentas: lazy(() => import("./views/Ferramentas")),
  tarefas: lazy(() => import("./views/Tarefas")),
  agenda: lazy(() => import("./views/Agenda")),
  conhecimento: lazy(() => import("./views/Conhecimento")),
  configuracoes: lazy(() => import("./views/Configuracoes")),
};

/* As rotas saem de NAV_ITEMS — a lista não é reescrita aqui. Se um item entrar
 * ou sair, ele entra ou sai em um lugar só. */
const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      ...NAV_ITEMS.map(({ id, path }) => {
        const Component = VIEWS[id];
        return path === "/"
          ? { index: true, element: <Component /> }
          : { path: path.slice(1), element: <Component /> };
      }),
      /* Rota de inspeção da assinatura. Fora de NAV_ITEMS de propósito e
         ausente do build de produção. */
      ...(AssinaturaPreview
        ? [{ path: "_assinatura", element: <AssinaturaPreview /> }]
        : []),
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
