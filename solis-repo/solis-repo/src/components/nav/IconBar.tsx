import { NavLink } from "react-router-dom";
import { NAV_ITEMS } from "../../lib/nav-items";
import "./IconBar.css";

/* Barra de ícones ("hotbar") — flutuante, só ícones.
 *
 * Medida em 01-conversa-inicio.png. Consome a MESMA NAV_ITEMS da Sidebar: a
 * lista não é redeclarada aqui, que foi a duplicação responsável pela
 * divergência entre as telas geradas.
 */
export function IconBar() {
  return (
    <nav className="iconbar" aria-label="Navegação principal">
      <ul className="iconbar__list">
        {NAV_ITEMS.map(({ id, label, path, Icon }) => (
          <li key={id}>
            <NavLink
              to={path}
              end={path === "/"}
              className="iconbar__link"
              title={label}
              aria-label={label}
            >
              <Icon size={24} strokeWidth={2} aria-hidden />
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
