import {
  MessageSquareMore,
  Brain,
  Box,
  ClipboardCheck,
  CalendarDays,
  BookOpen,
  Settings,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { ToolsCrossed } from "../components/icons/ToolsCrossed";

/* FONTE ÚNICA DE VERDADE DA NAVEGAÇÃO.
 *
 * Esta lista existe UMA vez. <Sidebar> e <IconBar> consomem daqui — nunca
 * redeclaram itens. Foi exatamente a duplicação que produziu a inconsistência
 * entre as telas geradas (uma com item a mais, outra com ordem diferente).
 *
 * Decisão confirmada pelo Matheus: a lista oficial é a de 8 itens do
 * solis-tokens.json → navigation.items, que bate com as telas 03, 05 e 06.
 * As telas 01 e 02 mostram uma navegação de 7 itens (sem "Modelos locais",
 * e a 02 ainda troca a ordem de Ferramentas/Tarefas/Agenda) — é a
 * inconsistência que o próprio JSON documenta em `_itemsNote`. Delas se
 * aproveita layout e visual, nunca a navegação.
 */

export interface NavItem {
  /** Identificador estável. Não muda com tradução de rótulo. */
  id: string;
  /** Rótulo em pt-BR, exatamente como aparece na referência. */
  label: string;
  /** Rota. */
  path: string;
  /** Ícone 24×24, stroke 2px, cap/join redondos (icon tokens). */
  Icon: LucideIcon | typeof ToolsCrossed;
}

export const NAV_ITEMS: readonly NavItem[] = [
  { id: "conversa", label: "Conversa", path: "/", Icon: MessageSquareMore },
  { id: "memoria", label: "Memória", path: "/memoria", Icon: Brain },
  { id: "modelos-locais", label: "Modelos locais", path: "/modelos-locais", Icon: Box },
  // Ícone desenhado à mão: o Lucide não tem chave + chave de fenda cruzadas.
  { id: "ferramentas", label: "Ferramentas", path: "/ferramentas", Icon: ToolsCrossed },
  { id: "tarefas", label: "Tarefas", path: "/tarefas", Icon: ClipboardCheck },
  { id: "agenda", label: "Agenda", path: "/agenda", Icon: CalendarDays },
  { id: "conhecimento", label: "Conhecimento", path: "/conhecimento", Icon: BookOpen },
  { id: "configuracoes", label: "Configurações", path: "/configuracoes", Icon: Settings },
] as const;

/** Estilos de navegação. O usuário escolhe em Configurações → Aparência. */
export type NavStyle = "sidebar" | "iconbar";

/* navigation.style.defaultOnFirstInstall — DECIDIDO: sidebar.
 * Não é mais fallback provisório; é o padrão de primeira instalação. */
export const NAV_STYLE_DEFAULT: NavStyle = "sidebar";
