# Solis — Alinhamento de Performance

Este projeto tem uma exigência que os outros não têm: leveza extrema e fluidez constante, mesmo com STT, TTS, visão computacional e LLM local competindo por CPU/GPU na mesma máquina. Isso muda decisões técnicas, não só de design. Este documento existe pra essas regras não se perderem entre hoje e amanhã.

## 1. Animação: só `transform` e `opacity`

**Regra:** qualquer animação que roda em loop (os 5 estados do Solis, principalmente `idle`, que fica ativo o tempo todo) só pode animar `transform` e `opacity`. Essas duas propriedades rodam no compositor da GPU, sem forçar repaint a cada frame.

**Proibido em loop infinito:** `filter`, `box-shadow`, `width`/`height`, propriedades de layout.

O protótipo de ontem (`solis-prototype.html`) usa `filter: drop-shadow` animado no estado `idle` — isso precisa ser reescrito antes de virar código de produção. Padrão correto pra simular o mesmo efeito visual de "respiração":

```css
/* Errado (força repaint a cada frame, todo frame, pra sempre): */
.state-idle .sun-core {
  animation: breathe 4.5s ease-in-out infinite;
}
@keyframes breathe {
  0%, 100% { filter: drop-shadow(0 0 6px rgba(255,183,77,0.5)); }
  50% { filter: drop-shadow(0 0 14px rgba(255,183,77,0.85)); }
}

/* Certo (só compositor, GPU-friendly): um elemento de glow separado,
   sobreposto ao núcleo, que anima opacity + scale em vez de filter) */
.glow-layer {
  position: absolute;
  inset: -40%;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(255,183,77,0.55), transparent 70%);
  animation: breathe 4.5s ease-in-out infinite;
  will-change: transform, opacity;
}
@keyframes breathe {
  0%, 100% { opacity: 0.4; transform: scale(0.9); }
  50%      { opacity: 0.8; transform: scale(1.1); }
}
```

O efeito visual final é equivalente — o glow "pulsa" — mas o custo pra GPU é ordens de grandeza menor porque não recalcula sombra a cada frame.

## 2. Fonte: sem dependência de rede

**Regra:** nada de `<link>` pra Google Fonts ou qualquer CDN de fonte em runtime. Duas opções:
- Self-host: baixar os arquivos `.woff2` da Inter e servir localmente dentro do bundle do Tauri.
- Ou simplesmente usar `system-ui` como fonte principal — zero peso, zero dependência, e ainda está dentro do "provisório" já sinalizado no token de tipografia.

Dado que a fonte final nem está travada ainda (ver `HANDOFF.md`), a opção mais simples pra amanhã é `system-ui` puro. Trocar depois é uma linha no CSS, não um refactor.

## 3. Ícones: import nomeado, nunca a biblioteca inteira

Se usar Lucide (recomendado no DS original, seção 11) pros ícones universais (Início, Pesquisar, Anexar etc.): importar só os ícones usados —

```ts
import { Home, Search, Paperclip } from "lucide-react"; // ok, tree-shake limpo
// nunca: import * as Icons from "lucide-react"
```

Os ícones exclusivos do Solis (símbolo, estados) continuam sendo SVG desenhado à mão, sem dependência de biblioteca — isso já está certo no protótipo de ontem.

## 4. Renderização: animação de estado é CSS, não JavaScript

Trocar de estado (`idle` → `listening` → `thinking`...) deve ser só troca de classe CSS. Nunca usar `setInterval`/`requestAnimationFrame` em JavaScript pra atualizar posição/opacidade frame a frame — isso teria custo de reconciliação do React a cada tick. O protótipo de ontem já faz certo (`element.className = ...`), só a curva de dentro da classe que precisa da correção do item 1.

## 5. Carregamento: cada tela é lazy

Com 6 telas (Início, Conversa, Memória, Foco, Ferramentas, Configurações), nenhuma delas deve estar no bundle inicial além da que abre primeiro:

```ts
const Chat = lazy(() => import("./views/Chat"));
const Memory = lazy(() => import("./views/Memory"));
// etc.
```

Isso mantém o tempo de abertura do app curto mesmo se alguma tela crescer (ex: Memória com muitos itens, histórico de conversa longo).

## 6. Tauri: não adicionar peso que ele já evitou

Tauri foi escolhido exatamente por ser mais leve que Electron (não empacota um Chromium inteiro). Não anular essa vantagem depois: evitar adicionar bibliotecas de UI pesadas (component libraries completas tipo Material UI ou Ant Design) — o design system do Solis já é a UI, então componentizar do zero com Tailwind é mais leve do que importar um kit de componentes genérico só pra sobrescrever tudo com CSS próprio depois.

## 7. Checklist rápido pra amanhã

- [ ] Trocar `filter: drop-shadow` animado por `glow-layer` com `opacity`/`transform`
- [ ] Remover `<link>` do Google Fonts, usar `system-ui` por enquanto
- [ ] Import nomeado de ícones (nunca `import *`)
- [ ] Lazy load de cada view
- [ ] Zero component library pesada — só Tailwind + componentes próprios
