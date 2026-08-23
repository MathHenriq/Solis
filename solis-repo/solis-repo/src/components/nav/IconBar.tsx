import { NavLink } from "react-router-dom";
import { NAV_ITEMS } from "../../lib/nav-items";

/* Barra de ícones ("hotbar") — flutuante, só ícones.
 *
 * ⚠️ ESTRUTURAL, SEM ESTILO FIEL AINDA. Mesma observação da Sidebar: o que
 * importa na Fase 0 é que as duas navegações consomem NAV_ITEMS, a mesma lista,
 * na mesma ordem. O visual sai na Fase 1, medido contra 01-conversa-inicio.png.
 *
 * Nota: a hotbar da referência 01 mostra 7 ícones, não 8. É a inconsistência
 * documentada em navigation._itemsNote e já resolvida: a lista oficial é a de
 * 8 itens. Da tela 01 se aproveita o layout da barra, nunca a lista.
 */
export function IconBar() {
  return (
    <nav aria-label="Navegação principal" data-nav="iconbar">
      <ul>
        {NAV_ITEMS.map(({ id, label, path, Icon }) => (
          <li key={id}>
            <NavLink to={path} end={path === "/"} title={label} aria-label={label}>
              <Icon size={24} strokeWidth={2} aria-hidden />
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
