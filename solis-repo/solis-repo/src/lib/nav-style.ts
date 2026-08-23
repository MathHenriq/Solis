import { useCallback, useEffect, useState } from "react";
import { NAV_STYLE_FALLBACK, type NavStyle } from "./nav-items";

/* Persistência da escolha de navegação (Sidebar ou Barra de ícones).
 *
 * HANDOFF.md: a escolha fica salva localmente, não é estado de sessão —
 * trocar de tela ou reabrir o app não pode resetar pro padrão.
 *
 * TODO(persistência): localStorage sobrevive ao restart e já cumpre o "não é
 * estado de sessão", mas mora dentro do webview. O destino é a config local do
 * app (Tauri store ou SQLite, junto com o resto das preferências). Trocar aqui
 * é trocar a implementação de duas funções, nada além.
 */
const KEY = "solis.nav-style";

function read(): NavStyle {
  try {
    const v = localStorage.getItem(KEY);
    return v === "sidebar" || v === "iconbar" ? v : NAV_STYLE_FALLBACK;
  } catch {
    return NAV_STYLE_FALLBACK;
  }
}

export function useNavStyle(): [NavStyle, (s: NavStyle) => void] {
  const [style, setStyleState] = useState<NavStyle>(read);

  useEffect(() => {
    document.documentElement.setAttribute("data-nav-style", style);
  }, [style]);

  const setStyle = useCallback((s: NavStyle) => {
    setStyleState(s);
    try {
      localStorage.setItem(KEY, s);
    } catch {
      /* sem storage, a escolha vale só pra sessão — não é motivo pra quebrar a UI */
    }
  }, []);

  return [style, setStyle];
}
