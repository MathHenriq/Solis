import { useEffect } from "react";

/* Variante do Horizonte (Camada 1).
 *
 * O horizonte vive no shell e não conhece as telas — é o que mantém as camadas
 * independentes. Mas a abertura da Conversa (01-conversa-inicio.png) mostra o
 * mesmo horizonte em escala de herói, enquanto as demais telas (02, 03, 05, 06)
 * mostram a versão discreta colada no rodapé.
 *
 * Em vez de passar prop pelo shell, a tela declara a variante que quer e o
 * horizonte lê. O elemento continua sendo o mesmo, montado uma vez: só a
 * geometria muda por variável CSS. Ao sair da tela, volta ao padrão.
 */
export type HorizonVariant = "default" | "hero";

export function useHorizonVariant(variant: HorizonVariant) {
  useEffect(() => {
    const el = document.querySelector(".horizon");
    if (!el) return;
    el.setAttribute("data-variant", variant);
    return () => el.setAttribute("data-variant", "default");
  }, [variant]);
}
