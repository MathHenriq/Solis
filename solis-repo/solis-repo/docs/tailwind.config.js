/** Solis Design System v0.1 — tokens traduzidos para Tailwind.
 *  Fonte: solis-tokens.json. Não adicionar valor aqui sem antes atualizar o JSON —
 *  ele continua sendo a fonte única de verdade, isso aqui é só a tradução pro Tailwind. */

/** @type {import('tailwindcss').Config} */
module.exports = {
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
      fontFamily: {
        // system-ui é a fonte ATIVA (ver PERFORMANCE.md: sem dependência de rede).
        // Inter fica listada só para quando/se for self-hosted — CSS não baixa fonte
        // por nome sozinho, então isso aqui não gera tráfego de rede.
        sans: ["system-ui", "-apple-system", "sans-serif"],
      },
      transitionTimingFunction: {
        solis: "cubic-bezier(0.45, 0, 0.2, 1)",
      },
      keyframes: {
        breathe: {
          "0%, 100%": { filter: "drop-shadow(0 0 6px rgba(255,183,77,0.5))" },
          "50%": { filter: "drop-shadow(0 0 14px rgba(255,183,77,0.85))" },
        },
        pulseFast: {
          "0%, 100%": { opacity: 0.4, transform: "scale(1)" },
          "50%": { opacity: 0.8, transform: "scale(1.05)" },
        },
        respondPulse: {
          "0%, 100%": { filter: "drop-shadow(0 0 10px rgba(255,183,77,0.7))", transform: "scale(1)" },
          "50%": { filter: "drop-shadow(0 0 22px rgba(255,183,77,1))", transform: "scale(1.06)" },
        },
      },
      animation: {
        // Durações PROVISÓRIAS — validadas só visualmente, não em produto real.
        "solis-idle": "breathe 4.5s ease-in-out infinite",
        "solis-listening": "pulseFast 1.6s ease-in-out infinite",
        "solis-responding": "respondPulse 1.1s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
