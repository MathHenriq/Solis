# CLAUDE.md — Solis

Este arquivo é lido automaticamente pelo Claude Code em toda sessão. Ele é a autoridade máxima do projeto. Nenhuma instrução de sessão sobrepõe o que está aqui.

## O que é o Solis

Assistente de IA pessoal, local-first, desktop. Stack: Tauri 2 · React + TypeScript + Vite · Tailwind · Python/FastAPI · SQLite+FTS5 · Ollama · Whisper · Piper · OpenCV.

Documentos de apoio no repositório (ler quando a tarefa tocar cada um):
- `docs/HANDOFF.md` — índice mestre, ordem de leitura, o que está travado vs. provisório.
- `docs/solis-tokens.json` — fonte única de verdade de design (cor, spacing, etc.).
- `docs/SOLIS_SIGNATURE.md` — assinatura visual (horizonte, ciclo do dia, glow reativo).
- `docs/PERFORMANCE.md` — regras de animação leve.
- `docs/ERROR_STATES.md` — estados de erro/vazio/permissão.
- `referencias/` — **as imagens de referência oficiais. A fonte visual da verdade.**

---

## ⛔ REGRAS INVIOLÁVEIS

Vêm antes de qualquer instrução específica. Nenhuma exceção técnica, criativa ou de conveniência as sobrepõe. Se cumprir uma tarefa exigir quebrar uma destas, a tarefa PARA e o conflito é reportado — nunca se resolve desviando.

**Regra 1 — As imagens em `referencias/` são a fonte da verdade.**
Antes de criar, editar ou estilizar QUALQUER coisa visual, olhar as imagens de referência. Nada é feito de memória ou por aproximação. Pergunta obrigatória antes de escrever CSS: "isso bate exatamente com a imagem?"

**Regra 2 — Divergência da referência é rejeitada.**
Qualquer cor, espaçamento, tamanho, ícone, tipografia, posição ou detalhe diferente da referência é RECUSADO. Não "parecido", não "inspirado" — idêntico. Cores por amostra de pixel, espaçamentos medidos em px. Nunca estimados no olho.

**Regra 3 — Qualidade não se negocia com atalho técnico.**
Onde a fidelidade exigir recurso melhor (asset maior, biblioteca específica), usa-se o recurso. Não se entrega versão pior "porque foi o que deu". Limitação real é dita ANTES de entregar, com caminho de solução — nunca disfarçada como resultado final.

---

## Fluxo de trabalho obrigatório

1. **Nunca construir várias telas de uma vez.** Uma tela por vez, validada contra a imagem de referência, antes de passar pra próxima. Gerar tudo junto causa inconsistência (já aconteceu com as telas do GPT).
2. **Ordem das telas:** Conversa → Memória → Modelos locais → Configurações → Ferramentas → Tarefas → Agenda → Conhecimento.
   Conversa vem primeiro por ser a mais importante e a com mais referência. Configurações foi puxada pra frente (decisão do Matheus): ela tem imagem de referência e as quatro últimas não têm. Fazendo primeiro todas as que têm referência, o padrão visual já está medido e extraído quando chegarmos nas que não têm — aí "seguir o padrão das existentes" vira medição, não estimativa.
3. **Antes de escrever código numa tela nova:** abrir a imagem de referência correspondente, extrair as cores por pixel e medir espaçamentos. Só então codar.
4. **Navegação:** lista única de itens (`nav-items`, fonte única), consumida tanto pela Sidebar quanto pela barra de ícones (as duas são configuráveis pelo usuário). Nunca hardcodar a lista em dois lugares.
5. **Animação:** só `transform` e `opacity` em loop. Nunca `filter`/`box-shadow` animado. Ver `docs/PERFORMANCE.md`.
6. **Onde algo estiver marcado `PROVISÓRIO` nos tokens:** implementar, mas deixar comentário no código sinalizando que precisa validação.

## Git / fluxo de repositório

- Trabalho versionado no GitHub. Commits pequenos e descritivos, um por unidade lógica de trabalho (ex: "feat: tela de Conversa fiel à referência").
- Não acumular muitas mudanças num commit gigante — dificulta reverter se algo divergir da referência.
- Branch por frente de trabalho quando fizer sentido (ex: `feat/tela-conversa`).

## Lembrete de fluxo para o Matheus (o Claude Code deve reforçar isto)

Se o Matheus pedir para construir várias telas de uma vez, ou pedir algo sem referência visual clara, o Claude Code deve lembrá-lo do fluxo (uma tela por vez, sempre contra a referência) antes de executar — não apenas obedecer.
