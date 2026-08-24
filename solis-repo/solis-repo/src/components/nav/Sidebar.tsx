import { NavLink } from "react-router-dom";
import { ChevronDown } from "lucide-react";
import { NAV_ITEMS } from "../../lib/nav-items";
import { SolisSymbol } from "../SolisSymbol/SolisSymbol";
import "./Sidebar.css";

/* Sidebar — fixa à esquerda, ícone + texto.
 *
 * Medida em 05-memoria.png e conferida em 02-conversa-thread.png. As medições
 * cruas e onde elas foram encaixadas na escala de spacing estão em Sidebar.css.
 *
 * A lista vem de NAV_ITEMS e não é redeclarada aqui. A navegação de 7 itens que
 * aparece em 01 e 02 é a inconsistência documentada em `_itemsNote` — dessas
 * telas se aproveita layout e visual, nunca a lista.
 */
export function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <SolisSymbol size="sm" />
        <span className="sidebar__wordmark">SOLIS</span>
      </div>

      <nav aria-label="Navegação principal">
        <ul className="sidebar__nav">
          {NAV_ITEMS.map(({ id, label, path, Icon }) => (
            <li key={id}>
              <NavLink to={path} end={path === "/"} className="sidebar__link">
                <Icon size={24} strokeWidth={2} aria-hidden />
                <span className="sidebar__label">{label}</span>
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <div className="sidebar__spacer" />

      {/* Dados do usuário ainda vêm da referência. Quando houver perfil real,
          isto passa a ler da config local — não é motivo pra travar a tela. */}
      <button type="button" className="sidebar__user">
        <span className="sidebar__avatar">MH</span>
        <span className="sidebar__user-info">
          <span className="sidebar__user-name">Matheus</span>
          <span className="sidebar__user-mail">matheus@email.com</span>
        </span>
        <ChevronDown size={20} strokeWidth={2} className="sidebar__user-chevron" aria-hidden />
      </button>
    </aside>
  );
}
