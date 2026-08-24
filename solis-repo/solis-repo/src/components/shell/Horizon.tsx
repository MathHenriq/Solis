import "./Horizon.css";

/* Camada 1 — Horizonte persistente.
 *
 * Renderizado uma vez no shell, atrás de todo conteúdo. Não recebe props de
 * estado de interação de propósito: esta camada não sabe se o usuário está
 * falando, e a Camada 2 (ciclo do dia) chega até aqui só por variável CSS.
 * Cada camada só sabe da que está embaixo dela — é isso que evita o sistema
 * virar uma bola de estado só, difícil de debugar.
 *
 * A arte é PROVISÓRIA. Ver o comentário no topo de Horizon.css.
 */
export function Horizon() {
  return (
    <div className="horizon" data-variant="default" aria-hidden="true">
      <div className="horizon__art horizon__art--image" />
      <div className="horizon__art">
        <div className="horizon__atmosphere" />
        <div className="horizon__curve" />
        <div className="horizon__ground" />
        <div className="horizon__line" />
        <div className="horizon__streak" />
        <div className="horizon__bloom" />
        <div className="horizon__sun" />
      </div>
    </div>
  );
}
