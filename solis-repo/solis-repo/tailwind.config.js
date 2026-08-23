/** Solis Design System v0.1 — tokens traduzidos para Tailwind.
 *  Fonte: docs/solis-tokens.json. Não adicionar valor aqui sem antes atualizar o
 *  JSON — ele continua sendo a fonte única de verdade, isso aqui é só a tradução.
 *
 *  ⚠️ CORREÇÃO APLICADA em relação à versão que estava em docs/tailwind.config.js:
 *  aquela versão animava `filter: drop-shadow` em `infinite` nos keyframes
 *  `breathe` e `respondPulse`. Isso é exatamente o padrão que PERFORMANCE.md
 *  seção 1 marca como ERRADO (força repaint a cada frame, pra sempre) e manda
 *  reescrever. É o mesmo bug que existia no protótipo e que sobreviveu na
 *  tradução pro Tailwind. Aqui todos os loops são compositor-only:
 *  só `transform` e `opacity`. O efeito visual é equivalente — o glow "pulsa" —
 *  mas o custo pra GPU é ordens de grandeza menor.
 */

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        solar: "#FFB74D",
        amber: "#F08A24",
        light: "#FFE3A6",
        night: "#071019",
        deep: "#0D1722",
        "warm-white": "#F5F0E7",
        muted: "#A1A7B3",
        success: "#8FBF6D",
        error: "#E4674A",
      },
      borderRadius: {
        sm: "8px",
        md: "12px",
        lg: "16px",
        pill: "999px",
      },
      spacing: {
        xs: "4px",
        sm: "8px",
        md: "12px",
        lg: "16px",
        xl: "24px",
        "2xl": "32px",
        "3xl": "48px",
        "4xl": "64px",
      },
      fontSize: {
        title1: ["32px", { lineHeight: "1.25" }],
        title2: ["20px", { lineHeight: "1.35" }],
        body: ["16px", { lineHeight: "1.5" }],
        caption: ["12px", { lineHeight: "1.4" }],
      },
      fontFamily: {
        // system-ui é a fonte ATIVA (PERFORMANCE.md: sem dependência de rede).
        // A fonte final segue PROVISÓRIA (Inter/Sora/Manrope/Poppins não decidida).
        // Trocar exige self-host de .woff2 no bundle, nunca <link> de CDN.
        sans: ["system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
      },
      transitionTimingFunction: {
        solis: "cubic-bezier(0.45, 0, 0.2, 1)",
      },
      keyframes: {
        // idle — "respiração". Camada de glow separada por trás do símbolo.
        breathe: {
          "0%, 100%": { opacity: "0.4", transform: "scale(0.9)" },
          "50%": { opacity: "0.8", transform: "scale(1.1)" },
        },
        // listening — pulso rápido. Já era compositor-only na versão original.
        pulseFast: {
          "0%, 100%": { opacity: "0.4", transform: "scale(1)" },
          "50%": { opacity: "0.8", transform: "scale(1.05)" },
        },
        // thinking — rotação sutil do arco + pulso do núcleo. rotate é transform.
        thinkingDrift: {
          "0%": { opacity: "0.45", transform: "rotate(0deg) scale(0.96)" },
          "50%": { opacity: "0.75", transform: "rotate(180deg) scale(1.04)" },
          "100%": { opacity: "0.45", transform: "rotate(360deg) scale(0.96)" },
        },
        // responding — pulso luminoso mais forte, sem filter.
        respondPulse: {
          "0%, 100%": { opacity: "0.55", transform: "scale(0.98)" },
          "50%": { opacity: "0.95", transform: "scale(1.12)" },
        },
        // Camada 1 — deriva do horizonte. Ciclo longo e variação mínima:
        // a pessoa não deve perceber a animação, só sentir que a tela não está morta.
        horizonDrift: {
          "0%, 100%": { transform: "scale(1)", opacity: "0.94" },
          "50%": { transform: "scale(1.015)", opacity: "1" },
        },
      },
      animation: {
        // Durações PROVISÓRIAS (solis-tokens.json → motion._status): vieram do
        // protótipo visual, nunca testadas com STT/visão/LLM competindo por GPU.
        "solis-idle": "breathe 4.5s cubic-bezier(0.45,0,0.2,1) infinite",
        "solis-listening": "pulseFast 1.6s cubic-bezier(0.45,0,0.2,1) infinite",
        "solis-thinking": "thinkingDrift 3s linear infinite",
        "solis-responding": "respondPulse 1.1s cubic-bezier(0.45,0,0.2,1) infinite",
        "solis-horizon": "horizonDrift 90s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
