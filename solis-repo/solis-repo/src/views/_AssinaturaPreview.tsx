import { SOLIS_STATES, SOLIS_STATE_LABELS, SolisSymbol } from "../components/SolisSymbol/SolisSymbol";

/* Página de inspeção da assinatura — SÓ EM DESENVOLVIMENTO.
 *
 * Não está em NAV_ITEMS e não entra no build de produção (a rota é registrada
 * atrás de import.meta.env.DEV). Existe pra conferir as 3 camadas sem precisar
 * de uma tela pronta: os 5 estados lado a lado, o nível de áudio simulado e o
 * comportamento com movimento reduzido.
 *
 * Isto NÃO é uma tela do produto e não serve de base pra nenhuma.
 */
export default function AssinaturaPreview() {
  return (
    <section style={{ padding: "24px", position: "relative", zIndex: 1 }}>
      <h1 style={{ fontSize: "var(--solis-title2-size)", margin: 0 }}>
        Assinatura — inspeção (dev)
      </h1>

      <div style={{ display: "flex", gap: "48px", marginTop: "32px", flexWrap: "wrap" }}>
        {SOLIS_STATES.map((state) => (
          <figure key={state} style={{ margin: 0, display: "grid", placeItems: "center", gap: "12px" }}>
            <SolisSymbol state={state} size="lg" />
            <figcaption style={{ color: "var(--solis-muted)", fontSize: "var(--solis-caption-size)" }}>
              {SOLIS_STATE_LABELS[state]}
            </figcaption>
          </figure>
        ))}
      </div>

      <label style={{ display: "block", marginTop: "40px", color: "var(--solis-muted)", fontSize: "var(--solis-caption-size)" }}>
        Simular nível de áudio (só afeta “Escutando”)
        <input
          type="range"
          min={0}
          max={1}
          step={0.01}
          defaultValue={0}
          style={{ display: "block", width: "260px", marginTop: "8px" }}
          onChange={(e) =>
            document.documentElement.style.setProperty("--solis-audio-level", e.target.value)
          }
        />
      </label>
    </section>
  );
}
