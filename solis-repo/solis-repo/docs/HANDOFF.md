# Solis — Handoff para Claude Code

Stack confirmada: Tauri 2 · React + TypeScript + Vite · Tailwind · Python/FastAPI · SQLite+FTS5 · Ollama · Whisper · Piper · OpenCV.

## Ordem de leitura recomendada

Não jogue todos os arquivos juntos na primeira mensagem do Claude Code sem contexto — a ordem importa porque documentos depois corrigem/restringem decisões dos anteriores.

1. **`Solis_Tokens_Complementares_v0.1.md`** — por que cada token de cor/radius/elevação é o que é (contraste calculado).
2. **`solis-tokens.json`** — fonte única de verdade em formato máquina: cor, radius, spacing, elevação, tipografia, ícone, símbolo, motion, estados, e a assinatura (horizonte/ciclo do dia/áudio).
3. **`tailwind.config.js`** — os mesmos tokens já traduzidos pro Tailwind. Não deve ter nenhum valor que não venha do JSON acima.
4. **`SOLIS_SIGNATURE.md`** — a assinatura visual oficial: horizonte persistente + ciclo do dia + glow reativo ao áudio. Muda a arquitetura de componentes (o símbolo não é mais um componente isolado, é 3 camadas).
5. **`PERFORMANCE.md`** — regras obrigatórias de leveza/fluidez. Ler antes de escrever qualquer CSS de animação — corrige erros que já existiam no protótipo visual.
6. **`ERROR_STATES.md`** — todo estado de vazio, erro e permissão (mic negado, Ollama fora do ar, memória vazia), com o texto exato e o tom de cada um.
7. **`solis-prototype.html`** — referência de comportamento executável. Abrir no navegador só depois de ler os itens acima, porque ele tem pelo menos uma implementação (o `filter: drop-shadow` animado) que o item 5 explicitamente corrige. Serve pra ver a navegação entre telas e a lógica de troca de estado — não pra copiar o CSS de animação.

## Navegação — configurável (Sidebar ou Barra de ícones)

Decisão confirmada: a navegação não é fixa em um único formato. O usuário escolhe entre dois em Configurações → Aparência:

- **Sidebar** — fixa à esquerda, ícone + texto, como nas telas de Conversa/Memória/Modelos locais/Configurações já geradas.
- **Barra de ícones** ("hotbar") — flutuante, só ícones, como na tela de Início gerada (bolinhas macOS + barra inferior arredondada).

**Implicação de arquitetura:** isso não é CSS condicional simples — são dois componentes de navegação distintos (`<Sidebar>` e `<IconBar>`) que precisam renderizar as mesmas 7 rotas (Conversa, Memória, Modelos locais, Ferramentas, Tarefas, Agenda, Conhecimento, Configurações) a partir da mesma fonte de dados, pra nunca repetir o problema que já aconteceu nas telas geradas — uma tela com um item de menu a mais/a menos que as outras. Definir a lista de itens de navegação **uma vez só**, em um único lugar (ex: `nav-items.ts`), e os dois componentes consomem dela — nunca hardcoded duas vezes.

Persistência: a escolha do usuário fica salva localmente (SQLite ou arquivo de config), não é só estado de sessão — trocar de tela ou reabrir o app não pode resetar pra o padrão.

Sem opinião fechada sobre qual vem selecionado por padrão na primeira instalação — fica em aberto pra decisão de produto, não é coisa que se resolve em documento.


> "Aqui estão os documentos do Solis (tokens, assinatura, performance, estados de erro). Monte a estrutura inicial do projeto em Tauri + React + TypeScript + Vite + Tailwind + FastAPI, seguindo `solis-tokens.json` como fonte de verdade — não inventar valor que não esteja lá. Onde o token estiver marcado `_status: PROVISÓRIO`, implementar mesmo assim, mas deixar comentário no código sinalizando que precisa validação. Seguir as regras de `PERFORMANCE.md` à risca em qualquer animação: só `transform`/`opacity` em loop, nunca `filter` contínuo."

Isso evita o erro mais comum nesse tipo de handoff: o agente "preencher lacunas" com valor plausível que vira fato consumado no código sem ninguém decidir de verdade.

## O que está travado vs. o que é provisório

**Travado (implementar direto, sem perguntar):**
- Paleta de cores e contraste (validado via WCAG — ver documento 1).
- Radius, spacing, elevação (superfície + borda, nunca box-shadow).
- Grid e stroke de ícone (24×24, stroke 2px, round cap/join).
- Ordem e nomes dos 5 estados do Solis (repouso/escutando/pensando/respondendo/executando).
- As 3 camadas da assinatura (horizonte, ciclo do dia, áudio reativo) e sua separação de responsabilidade.
- Regra de animação compositor-only (`transform`/`opacity`).
- Fonte ativa: `system-ui` (sem dependência de rede).

**Provisório (implementar, mas sinalizar no código com comentário):**
- Se a fonte final não for `system-ui` (DS original nunca fechou entre Inter/Sora/Manrope/Poppins) — trocar exige self-host, não CDN.
- Duração exata das animações em ms (vieram do protótipo visual, nunca testadas em produto real rodando junto com STT/visão).
- Timing da sequência de loading (núcleo → expansão → fechamento).
- Textos de `ERROR_STATES.md` — o tom está definido, a redação exata pode mudar com uso real.

## Símbolo oficial — RESOLVIDO (mudança de abordagem)

A pendência de "vetorizar o símbolo" foi resolvida, mas não do jeito originalmente planejado. Em vez de um SVG vetorial com camadas separadas (`horizon`/`sun`/`glow` editáveis), a marca final é uma **imagem raster (PNG) gerada e aprovada pelo Matheus**, em `brand/`:

```
brand/
├── logo/solis-logo-horizontal.png, solis-logo-vertical.png
├── symbol/solis-symbol-square.png, -wide.png,
│          solis-symbol-mono-transparent.png (+ -alt) ← únicas com transparência real
├── states/solis-state-listening.png, -rings-soft.png, -rings-strong.png
└── app-icon/solis-app-icon.png
```

**Consequência técnica real, não cosmética:** a Camada 3 do `SOLIS_SIGNATURE.md` (glow reativo ao áudio) não pode mais recortar/animar uma parte interna da arte, porque a arte é um PNG achatado. A solução aplicada no protótipo: uma camada CSS separada (`.symbol-glow`, gradiente radial com blur) fica **atrás** da imagem e reage a `--audio-level`; a arte aprovada nunca é tocada. Ver implementação em `solis-prototype.html`.

**Lacuna ainda aberta:** não existe um asset aprovado pro estado "Executando" (intensidade máxima) que respeite a regra "sem raios de sol" (DS seção 3.1) — a única imagem gerada nesse nível de intensidade tem raios, o que contraria a marca. O protótipo está reaproveitando `solis-state-rings-strong.png` como placeholder até isso ser gerado.

**Atenção de implementação:** só `solis-symbol-mono-transparent.png` (e sua variante `-alt`) têm canal alpha real. Os demais (`square`, `wide`, os 3 de `states/`) têm fundo preto sólido embutido — funcionam bem sobre `color.bg.canvas` (Night) por coincidência de cor, mas vão mostrar uma borda quadrada sobre qualquer outro fundo (ex: cards `color.bg.surface`/Deep). Não usar esses arquivos livremente sobre fundos variados sem antes pedir versão com transparência real.

## Estrutura de pastas sugerida (DS original, seção 22, adaptada pra stack confirmada)

```
solis/
├── src-tauri/                     → shell nativo (Tauri)
├── src/                           → frontend React
│   ├── components/
│   │   ├── SolisSymbol/           → horizon + sun + glow como sub-componentes separados
│   │   ├── buttons/ cards/ inputs/
│   ├── views/                     → Início, Conversa, Memória, Foco, Ferramentas, Configurações (lazy loaded)
│   ├── hooks/                     → useAudioLevel (Web Audio API), useDayCycle
│   └── styles/tokens.css
├── backend/                       → Python/FastAPI
│   ├── stt/ (Whisper) tts/ (Piper) vision/ (OpenCV)
│   ├── memory/ (SQLite+FTS5)
│   └── llm/ (Ollama)
└── design/                        → SVGs oficiais do símbolo quando vetorizados
```
