import { useEffect, useState } from "react";

/* Camada 2 da assinatura — ciclo do dia.
 *
 * A cor do horizonte e a posição do sol no arco mudam com a hora real do
 * dispositivo. Não é decoração: é o "nascer do sol" do conceito de marca.
 *
 * REGRA DE TOKEN (SOLIS_SIGNATURE.md): nenhum hex novo nasce aqui. Cada fase é
 * composição/opacidade dos tokens que já existem. Se uma fase parecer "sem
 * graça", o ajuste é na opacidade — nunca inventar cor.
 *
 * Esta camada não sabe se o usuário está falando. Ela só sabe que horas são.
 * É isso que evita o sistema virar uma bola de estado só.
 */

export type DayPhaseName =
  | "madrugada"
  | "amanhecer"
  | "dia"
  | "entardecer"
  | "noite";

/** Nome de token de cor — só valores que existem em solis-tokens.json → color. */
export type ColorToken = "night" | "deep" | "amber" | "solar" | "light" | "muted";

export interface DayPhase {
  name: DayPhaseName;
  /** [início, fim) em horas locais. */
  hours: readonly [number, number];
  colors: readonly [ColorToken, ColorToken];
  /** 0 = base do arco (sol quase invisível), 1 = topo do arco. */
  sunArcPosition: number;
  /** 0..1 — intensidade do glow do horizonte nessa fase. */
  glowIntensity: number;
}

/* Espelha solis-tokens.json → signature.dayCycle.phases, na mesma ordem. */
export const DAY_PHASES: readonly DayPhase[] = [
  { name: "madrugada", hours: [0, 5], colors: ["night", "deep"], sunArcPosition: 0.05, glowIntensity: 0.05 },
  { name: "amanhecer", hours: [5, 8], colors: ["amber", "night"], sunArcPosition: 0.35, glowIntensity: 0.4 },
  { name: "dia", hours: [8, 17], colors: ["solar", "light"], sunArcPosition: 1.0, glowIntensity: 1.0 },
  { name: "entardecer", hours: [17, 20], colors: ["amber", "deep"], sunArcPosition: 0.35, glowIntensity: 0.4 },
  { name: "noite", hours: [20, 24], colors: ["muted", "deep"], sunArcPosition: 0.05, glowIntensity: 0.05 },
] as const;

export function phaseForHour(hour: number): DayPhase {
  for (const phase of DAY_PHASES) {
    const [start, end] = phase.hours;
    if (hour >= start && hour < end) return phase;
  }
  // Só alcançável se a hora vier fora de 0..23. Cai na madrugada por segurança.
  return DAY_PHASES[0];
}

/** Milissegundos até a virada da próxima hora — evita acordar de minuto em minuto. */
export function msUntilNextHour(now: Date): number {
  const next = new Date(now);
  next.setHours(now.getHours() + 1, 0, 0, 0);
  return next.getTime() - now.getTime();
}

/**
 * Relógio compartilhado: devolve a hora local e se atualiza na virada de cada
 * hora. É a única fonte de hora do app — quem precisa reagir ao horário (o
 * ciclo do dia, a saudação da Conversa) lê daqui em vez de chamar `new Date()`
 * por conta própria, senão duas partes da interface podem discordar sobre que
 * horas são no minuto da virada.
 */
export function useHourTick(): number {
  const [hour, setHour] = useState(() => new Date().getHours());

  useEffect(() => {
    let timer = 0;

    const tick = () => {
      const now = new Date();
      setHour(now.getHours());
      // Reagenda pra virada da próxima hora, e não num intervalo fixo:
      // um app aberto o dia todo não precisa acordar 1440 vezes.
      timer = window.setTimeout(tick, msUntilNextHour(now) + 1000);
    };

    tick();
    return () => window.clearTimeout(timer);
  }, []);

  return hour;
}

/**
 * Aplica a fase atual como variáveis CSS no <html> e devolve a fase.
 *
 * As variáveis são lidas pelo Horizonte (Camada 1). A troca é discreta na
 * fronteira da fase, exatamente como o JSON especifica — os documentos não
 * definem interpolação entre fases, então não foi inventada nenhuma.
 * PENDENTE: se a virada entre fases ficar perceptível demais no uso real,
 * vale decidir uma transição suave — é decisão de produto, não de código.
 */
export function useDayCycle(): DayPhase {
  const phase = phaseForHour(useHourTick());

  useEffect(() => {
    const root = document.documentElement.style;
    root.setProperty("--solis-day-phase", phase.name);
    root.setProperty("--solis-day-sun-position", String(phase.sunArcPosition));
    root.setProperty("--solis-day-glow-intensity", String(phase.glowIntensity));
    root.setProperty("--solis-day-color-a", `var(--solis-${phase.colors[0]})`);
    root.setProperty("--solis-day-color-b", `var(--solis-${phase.colors[1]})`);
  }, [phase]);

  return phase;
}
