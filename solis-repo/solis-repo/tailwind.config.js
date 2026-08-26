/** Solis Design System — tokens traduzidos para Tailwind.
 *  Fonte: solis-tokens.json. Não adicionar valor aqui sem antes atualizar o JSON —
 *  ele continua sendo a fonte única de verdade, isso aqui é só a tradução pro Tailwind.
 *
 *  Cor de tema NÃO entra aqui como hex. Os 3 temas vivem em design/tokens.css
 *  (gerado do mesmo JSON) como custom properties trocadas por [data-theme]; aqui
 *  elas entram só como referência a var(), pra que uma classe do Tailwind continue
 *  válida em qualquer tema sem precisar de variante por tema. */

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Paleta base — independente de tema.
        solar: "#FFB74D",
        amber: "#F08A24",
        light: "#FFE3A6",
        night: "#071019",
        deep: "#0D1722",
        "warm-white": "#F5F0E7",
        muted: "#A1A7B3",
        success: "#8FBF6D",
        error: "#E4674A",

        // Papéis semânticos — o valor vem do tema ativo, ver design/tokens.css.
        canvas: "var(--canvas)",
        divider: "var(--divider)",
        "text-primary": "var(--text-primary)",
        "text-secondary": "var(--text-secondary)",
        "text-placeholder": "var(--text-placeholder)",
        accent: "var(--accent)",
      },
      borderRadius: {
        sm: "8px",
        md: "12px",
        lg: "16px",
        pill: "999px",
        composer: "var(--composer-radius)",
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
      width: {
        sidebar: "var(--sidebar-width)",
      },
      height: {
        composer: "var(--composer-height)",
        chip: "var(--chip-height)",
      },
      fontSize: {
        // hero é a saudação ("Olá, Matheus.") — único lugar da serifada.
        hero: ["var(--text-hero)", { fontWeight: 400 }],
        title1: ["32px", { fontWeight: 600 }],
        title2: ["20px", { fontWeight: 500 }],
        body: ["16px", { fontWeight: 400 }],
        caption: ["12px", { fontWeight: 400 }],
        "nav-label": "var(--sidebar-label)",
      },
      fontFamily: {
        // system-ui é a fonte ATIVA (ver PERFORMANCE.md: sem dependência de rede).
        // Inter fica listada só para quando/se for self-hosted — CSS não baixa fonte
        // por nome sozinho, então isso aqui não gera tráfego de rede.
        sans: ["system-ui", "-apple-system", "sans-serif"],
        // PROVISÓRIO: a serifada específica não foi escolhida. Quando for, vai
        // exigir self-host no bundle do Tauri, pelo mesmo motivo acima.
        display: ["var(--font-display)", "Georgia", "serif"],
      },
      transitionTimingFunction: {
        solis: "cubic-bezier(0.45, 0, 0.2, 1)",
      },
      keyframes: {
        // PERFORMANCE.md: só transform e opacity em loop. Estes keyframes usavam
        // `filter: drop-shadow` animado — que é exatamente a implementação do
        // protótipo que o PERFORMANCE.md corrige (ver HANDOFF.md, item 7 da ordem
        // de leitura). O glow deixa de ser filtro e passa a ser uma camada própria
        // atrás da arte, que só muda opacidade e escala.
        breathe: {
          "0%, 100%": { opacity: "0.55", transform: "scale(1)" },
          "50%": { opacity: "0.9", transform: "scale(1.04)" },
        },
        pulseFast: {
          "0%, 100%": { opacity: "0.4", transform: "scale(1)" },
          "50%": { opacity: "0.8", transform: "scale(1.05)" },
        },
        respondPulse: {
          "0%, 100%": { opacity: "0.7", transform: "scale(1)" },
          "50%": { opacity: "1", transform: "scale(1.06)" },
        },
        horizonDrift: {
          "0%, 100%": { opacity: "0.94", transform: "scale(1)" },
          "50%": { opacity: "1", transform: "scale(1.015)" },
        },
      },
      animation: {
        // Durações PROVISÓRIAS — validadas só visualmente, não em produto real.
        "solis-idle": "breathe 4.5s ease-in-out infinite",
        "solis-listening": "pulseFast 1.6s ease-in-out infinite",
        "solis-responding": "respondPulse 1.1s ease-in-out infinite",
        // 90s por decisão do SOLIS_SIGNATURE.md: o horizonte fica visível o tempo
        // todo, então qualquer ciclo perceptível vira irritante.
        "solis-horizon": "horizonDrift 90s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
