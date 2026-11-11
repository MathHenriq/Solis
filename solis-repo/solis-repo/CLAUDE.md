# CLAUDE.md — Solis

Este arquivo é lido automaticamente pelo Claude Code em toda sessão. Ele é a autoridade máxima do projeto. Nenhuma instrução de sessão sobrepõe o que está aqui.

## O que é o Solis

Assistente de IA pessoal, local-first, desktop. Stack: Tauri 2 · React + TypeScript + Vite · Tailwind · Python/FastAPI · SQLite+FTS5 · Ollama · Whisper · Piper · OpenCV.

Documentos de apoio no repositório (ler quando a tarefa tocar cada um):
- `docs/VISAO.md` — **ler antes de tudo**: o que o Solis é e pra onde vai, nas palavras do Matheus, e a barra de qualidade.
- `docs/PARIDADE.md` — o primeiro marco: tudo que o Claude Desktop e o Claude Code têm, o estado de cada coisa no Solis e a ordem. É o foco agora.
- `docs/ESCOPO.md` — **ler primeiro**: o que já existe, o que é provisório e a ordem das próximas fases.
- `backend/README.md` — o servidor local: como ligar, rotas, como a memória funciona.
- `docs/HANDOFF.md` — índice mestre, ordem de leitura, o que está travado vs. provisório.
- `docs/solis-tokens.json` — fonte única de verdade de design (cor, spacing, etc.).
- `docs/SOLIS_SIGNATURE.md` — assinatura visual (horizonte, ciclo do dia, glow reativo).
- `docs/PERFORMANCE.md` — regras de animação leve.
- `docs/ERROR_STATES.md` — estados de erro/vazio/permissão.
- `referencias/` — as imagens de referência oficiais: a verdade das telas que foram construídas e aprovadas por elas.

---

## ⛔ REGRAS INVIOLÁVEIS

Vêm antes de qualquer instrução específica. Nenhuma exceção técnica, criativa ou de conveniência as sobrepõe. Se cumprir uma tarefa exigir quebrar uma destas, a tarefa PARA e o conflito é reportado — nunca se resolve desviando.

**Regra 1 — Referência aprovada manda; o que é novo é desenhado com o Claude como base.**
Onde uma tela foi construída e aprovada contra uma imagem de `referencias/`, a imagem continua sendo a verdade dela: não se muda sem o Matheus pedir. Para o que é novo (tela, estado, componente) não é preciso esperar imagem: desde 08/11/2026 o Matheus liberou o front, porque as referências geradas não estavam saindo boas. A base é o próprio Claude (claude.ai e o app): proporção e estilo discretos, sem caixas e bordas pesadas, a conversa numa coluna central. Quando o Matheus pede um ajuste ("use o Claude como base", "ficou forçado"), o pedido dele vale sobre a referência antiga.

**Regra 2 — Medida, não olho.**
Com referência ou sem, nada é estimado. Contra uma referência: cores por amostra de pixel, espaçamentos medidos em px, e divergência sem pedido é RECUSADA. Em desenho próprio: os valores saem do design system já construído (tokens, a grade das telas validadas) e vão pro `docs/solis-tokens.json` com a razão, marcados como desenho próprio/PROVISÓRIO; depois de construir, os prints do app são medidos, conferidos nos 3 temas e nos 2 modos de navegação, e mostrados ao Matheus antes de seguir.

**Regra 3 — Qualidade não se negocia com atalho técnico.**
Onde a fidelidade exigir recurso melhor (asset maior, biblioteca específica), usa-se o recurso. Não se entrega versão pior "porque foi o que deu". Limitação real é dita ANTES de entregar, com caminho de solução — nunca disfarçada como resultado final.

---

## Fluxo de trabalho obrigatório

1. **Nunca construir várias telas de uma vez.** Uma tela por vez, validada contra a imagem de referência, antes de passar pra próxima. Gerar tudo junto causa inconsistência (já aconteceu com as telas do GPT).
2. **Ordem das telas:** Conversa primeiro (mais importante e com mais referência), depois Memória, Modelos locais, Ferramentas, Tarefas, Agenda, Conhecimento, Configurações.
3. **Antes de escrever código numa tela nova:** se houver referência, abrir a imagem, extrair as cores por pixel e medir espaçamentos; se não houver, partir do Claude e da grade das telas já validadas, e registrar as medidas nos tokens. Nos dois casos: print do app, medição, os 3 temas e os 2 modos de navegação antes do commit.
4. **Navegação:** lista única de itens (`nav-items`, fonte única), consumida tanto pela Sidebar quanto pela barra de ícones (as duas são configuráveis pelo usuário). Nunca hardcodar a lista em dois lugares.
5. **Animação:** só `transform` e `opacity` em loop. Nunca `filter`/`box-shadow` animado. Ver `docs/PERFORMANCE.md`.
6. **Onde algo estiver marcado `PROVISÓRIO` nos tokens:** implementar, mas deixar comentário no código sinalizando que precisa validação.

## Git / fluxo de repositório

- Trabalho versionado no GitHub. Commits pequenos e descritivos, um por unidade lógica de trabalho (ex: "feat: tela de Conversa fiel à referência").
- Não acumular muitas mudanças num commit gigante — dificulta reverter se algo divergir da referência.
- Branch por frente de trabalho quando fizer sentido (ex: `feat/tela-conversa`).

## Lembrete de fluxo para o Matheus (o Claude Code deve reforçar isto)

Se o Matheus pedir para construir várias telas de uma vez, o Claude Code deve lembrá-lo do fluxo (uma tela por vez, validada antes da próxima) antes de executar — não apenas obedecer. Pedido sem referência visual não bloqueia mais: desenha-se com o Claude como base (Regra 1) e os prints vão pra aprovação dele.
