import "./SolisSymbol.css";

/* Os 5 estados, na ordem e com os nomes travados em solis-tokens.json → states. */
export const SOLIS_STATES = [
  "idle",
  "listening",
  "thinking",
  "responding",
  "executing",
] as const;

export type SolisState = (typeof SOLIS_STATES)[number];

/** Rótulos pt-BR — travados no JSON, não reescrever aqui. */
export const SOLIS_STATE_LABELS: Record<SolisState, string> = {
  idle: "Repouso",
  listening: "Escutando",
  thinking: "Pensando",
  responding: "Respondendo",
  executing: "Executando",
};

/** Tamanhos de marca (symbol.size). Compartilham a base com icon.size. */
export type SymbolSize = "sm" | "md" | "lg" | "xl";

const SIZE_VAR: Record<SymbolSize, string> = {
  sm: "var(--solis-symbol-sm)",
  md: "var(--solis-symbol-md)",
  lg: "var(--solis-symbol-lg)",
  xl: "var(--solis-symbol-xl)",
};

interface Props {
  state?: SolisState;
  size?: SymbolSize;
  className?: string;
  /** Quando o símbolo é decorativo ao lado de um rótulo textual do estado. */
  decorative?: boolean;
}

/**
 * Símbolo do Solis com glow reativo.
 *
 * A troca de estado é troca de atributo — o CSS resolve o resto. Nenhuma
 * animação é dirigida por JavaScript frame a frame.
 *
 * O glow em `listening` lê --solis-audio-level, que o useAudioLevel escreve
 * a partir da Web Audio API. O símbolo não conhece o microfone.
 */
export function SolisSymbol({
  state = "idle",
  size = "md",
  className,
  decorative = true,
}: Props) {
  return (
    <span
      className={["solis-symbol", className].filter(Boolean).join(" ")}
      data-state={state}
      style={{ ["--symbol-size" as string]: SIZE_VAR[size] }}
      role={decorative ? undefined : "img"}
      aria-hidden={decorative || undefined}
      aria-label={decorative ? undefined : `Solis — ${SOLIS_STATE_LABELS[state]}`}
    >
      <span className="solis-symbol__glow" />
      <span className="solis-symbol__art" />
    </span>
  );
}
