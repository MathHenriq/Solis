import { NavLink } from "react-router-dom";
import { NAV_ITEMS } from "../../lib/nav-items";

/* Sidebar — fixa à esquerda, ícone + texto.
 *
 * ⚠️ ESTRUTURAL, SEM ESTILO FIEL AINDA. Este componente existe na Fase 0 pra
 * provar a arquitetura: ele e a IconBar leem a MESMA lista (NAV_ITEMS) e nunca
 * redeclaram itens. O visual (larguras, espaçamentos, cor do item ativo, a
 * barra âmbar da direita) é medido contra 02/03/05/06 na Fase 1, junto com a
 * tela de Conversa. Não estilizar isto "de memória" antes disso.
 */
export function Sidebar() {
  return (
    <nav aria-label="Navegação principal" data-nav="sidebar">
      <ul>
        {NAV_ITEMS.map(({ id, label, path, Icon }) => (
          <li key={id}>
            <NavLink to={path} end={path === "/"}>
              <Icon size={24} strokeWidth={2} aria-hidden />
              <span>{label}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
