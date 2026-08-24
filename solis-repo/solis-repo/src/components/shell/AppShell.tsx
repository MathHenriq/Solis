import { Suspense } from "react";
import { Outlet } from "react-router-dom";
import { Horizon } from "./Horizon";
import { Sidebar } from "../nav/Sidebar";
import { IconBar } from "../nav/IconBar";
import { useDayCycle } from "../../hooks/useDayCycle";
import { useNavStyle } from "../../lib/nav-style";
import "./AppShell.css";

/* Shell do app.
 *
 * O Horizonte (Camada 1) é montado AQUI, uma vez, e nunca é filho de uma view.
 * Se ele fosse montado dentro de cada tela, seria remontado a cada navegação —
 * e sendo uma cena grande, isso é custo real, não teórico.
 *
 * O ciclo do dia (Camada 2) é ligado aqui pelo mesmo motivo: ele publica
 * variáveis CSS na raiz do documento, então precisa viver acima das telas.
 *
 * As duas navegações são componentes distintos, não CSS condicional — e ambas
 * leem a mesma NAV_ITEMS.
 */
export function AppShell() {
  useDayCycle();
  const [navStyle] = useNavStyle();

  return (
    <div className="solis-shell">
      <Horizon />

      {navStyle === "sidebar" ? <Sidebar /> : <IconBar />}

      <main className="solis-shell__main">
        {/* Cada view é lazy: nenhuma tela entra no bundle inicial além da que
            abre primeiro (PERFORMANCE.md seção 5). */}
        <Suspense fallback={null}>
          <Outlet />
        </Suspense>
      </main>
    </div>
  );
}
