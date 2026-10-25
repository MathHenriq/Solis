# Escopo do Solis — onde estamos e para onde vamos

Documento vivo. Atualizar ao fechar cada fase. Última revisão: outubro de 2026.

## A visão

Um assistente pessoal que conhece o Matheus por inteiro: tudo o que ele manda é guardado,
tudo o que ele diz é entendido no contexto da vida dele, e o histórico é completo. Roda no
computador dele, sem nuvem, e se fala com ele por voz.

**O que isso entrega e o que não entrega.** A vantagem do Solis sobre um ChatGPT ou um
Claude é o **contexto**: ele sabe da Syngenta, dos estudos, das preferências, sem que nada
precise ser repetido. Ele **não** raciocina melhor que esses modelos. Um modelo local de 3B a
14B é muito menor que um modelo de nuvem de ponta, e isso aparece em perguntas difíceis.
O que dá pra fazer é escolher o maior modelo que a GPU aguenta e deixar a **busca de
contexto** fazer o trabalho pesado: um modelo médio com o contexto certo responde melhor
sobre a vida do Matheus do que um modelo enorme sem contexto nenhum.

## Arquitetura hoje

```
┌─────────────── Notebook do Matheus ───────────────┐
│                                                   │
│  Front (React, Vite)  ──HTTP──►  Servidor (FastAPI, 127.0.0.1:8765)
│  as 8 telas                       │        │
│                                   │        └──► SQLite (%APPDATA%\Solis\solis.db)
│                                   │             conversas · mensagens · memorias
│                                   └──► Ollama (127.0.0.1:11434)
│                                        os modelos de linguagem
└───────────────────────────────────────────────────┘
```

Tudo escuta só em `127.0.0.1`: nada sai da máquina e nada entra pela rede.

## O que já foi feito

### Front — fechado

- As 8 telas, construídas uma por vez contra as referências de `referencias/`.
- 3 temas (espacial, claro, dark) e 2 modos de navegação (sidebar e barra de ícones).
- Verificação automática: `npm run varrer` testa 96 combinações (telas × temas × modos ×
  tamanhos de janela) e `npm run checar` trava as regras que já foram quebradas antes.
- Preview na Vercel (só a casca visual; lá não há servidor).

### Servidor — primeira camada no ar

| O quê | Como funciona |
|---|---|
| Modelos locais | Lê do Ollama o que está instalado; clicar numa linha escolhe o modelo da Conversa |
| Conversa | A resposta chega em streaming; markdown vira parágrafo, lista e negrito |
| Histórico | Toda mensagem vai pro SQLite; o app reabre na última conversa; `/nova` começa outra |
| Memória | Automática (o modelo extrai fatos depois de cada resposta) e garantida quando pedida ("grave", "anote"...) |
| Prompt honesto | O prompt de sistema diz o que o Solis **não** consegue fazer, pra ele não inventar |
| Erros | Cada falha diz quem falhou: servidor, Ollama ou falta de modelo |

21 testes automáticos no servidor, rodando sem precisar do Ollama.

### O que ainda é provisório

- Tarefas, Agenda, Conhecimento e Ferramentas mostram dados de exemplo.
- Todas as memórias vão inteiras em todo pedido ao modelo (ver Fase 3).
- O histórico da conversa também vai inteiro.
- O servidor precisa ser ligado à mão (`npm run backend`).
- Não há controle na tela pra esquecer uma memória nem pra voltar a conversas antigas.

## Para onde vamos

A ordem segue uma regra: **primeiro o que torna o Solis útil, depois o que o torna
impressionante.** Voz sobre um assistente que esquece as coisas é só um assistente que
esquece as coisas, falando.

### Fase 3 — Contexto que escala (próxima; dá pra fazer sem o notebook)

Hoje toda memória entra em todo pedido. Com centenas delas, o pedido passa da janela de
contexto do modelo, o Ollama corta o começo sem avisar, e o Solis "esquece".

- **Busca por significado (RAG) nas memórias.** Cada memória vira um vetor de números
  (embedding, com o `nomic-embed-text`). A mensagem nova também. Só entram no pedido as
  memórias mais parecidas com a mensagem, por similaridade de cosseno. Os vetores ficam no
  próprio SQLite.
- **Janela do histórico.** Só as últimas mensagens vão inteiras; o começo de uma conversa
  longa vira um resumo.
- **Busca textual (FTS5)** na tela de Memória.
- **Desligar o raciocínio oculto** dos modelos que "pensam" (qwen3), pra responderem mais
  rápido.

### Fase 4 — Controle sobre a memória

Memória automática erra. Sem controle, ela vira lixo acumulado.

- Esquecer e corrigir uma memória pela tela (precisa de referência visual).
- Contradição: quando chega "saí da Syngenta", a memória antiga é substituída, não somada.
- Lista de conversas antigas (precisa de referência visual).

### Fase 5 — Conhecimento: os seus arquivos

"Tudo que eu mando ele salva" inclui documentos. A tela Conhecimento passa a indexar PDFs,
notas e textos: cada arquivo é cortado em trechos, cada trecho vira vetor, e entra no mesmo
mecanismo de busca da Fase 3. É aqui que o Solis passa a saber do que está nos arquivos, e
não só do que foi dito na conversa.

### Fase 6 — Voz

Detalhado abaixo, porque é onde está a dúvida da GPU.

1. **Apertar pra falar** primeiro: um botão ou atalho grava, solta e transcreve. Valida a
   transcrição e a voz sem a complexidade da escuta contínua.
2. **Escuta contínua com palavra de ativação** ("Solis") depois.
3. **Camada 3 da assinatura**: o glow do símbolo reagindo ao áudio (`docs/SOLIS_SIGNATURE.md`).

### Fase 7 — App de verdade

- O Tauri sobe o servidor sozinho (o Python empacotado como sidecar).
- Instalador `.msi`, inicia com o Windows.

### Depois

- **Ferramentas:** Agenda e Tarefas reais, ler arquivos com permissão.
- **Visão** (OpenCV, já na stack): o Solis olhar a tela ou a câmera quando pedido.

## Voz e a GPU: como funciona a escuta contínua

A preocupação: "pra me ouvir o tempo todo, uma LLM tem que ficar rodando e vai comer a
placa de vídeo". Não precisa. Assistentes de voz resolvem isso em **camadas**, e só a
primeira fica ligada o tempo todo:

| Camada | O que faz | Roda | Custo |
|---|---|---|---|
| 1. Palavra de ativação | Só reconhece "Solis". Não entende mais nada | **Sempre**, na CPU | Mínimo: um modelo minúsculo |
| 2. Detector de voz (VAD) | Sabe quando você começou e parou de falar | Depois da ativação, CPU | Mínimo |
| 3. Transcrição (Whisper) | Transforma o áudio em texto | Só no trecho que você falou | Segundos de GPU ou CPU, depois para |
| 4. Modelo de linguagem | Pensa a resposta | Só quando há pergunta | O de hoje |
| 5. Voz (TTS) | Lê a resposta em voz alta | Só enquanto fala | Pequeno; o Kokoro roda até na CPU |

A camada 1 é parecida com o "Ok Google" do celular: um modelo de poucos megabytes treinado
pra uma palavra só, que roda na CPU sem a GPU perceber. Nada de LLM ligada o tempo todo. A
GPU só trabalha nos segundos depois que você diz "Solis".

**O LLM também não fica na GPU pra sempre.** O Ollama descarrega o modelo depois de alguns
minutos parado (configurável). O preço disso: a primeira resposta depois de uma pausa
demora mais, porque o modelo precisa ser carregado de novo. Dá pra escolher entre "GPU
livre" e "resposta instantânea" — é uma configuração, não uma limitação.

**O que ainda precisa ser medido no notebook:** quanta memória de vídeo (VRAM) a GPU tem.
Whisper, LLM e voz disputam a mesma memória. Pra ver: Gerenciador de Tarefas → Desempenho →
GPU → "Memória dedicada da GPU". Esse número decide qual modelo de linguagem e qual Whisper
cabem juntos.

### Candidatos (nada fechado — escolher medindo)

| Função | Candidatos | Observação |
|---|---|---|
| Palavra de ativação | openWakeWord (aberto, aceita palavra própria), Porcupine (comercial) | Treinar "Solis" é possível no openWakeWord |
| Detector de voz | Silero VAD | Já vem junto do openWakeWord e do faster-whisper |
| Transcrição | faster-whisper (Whisper otimizado), whisper.cpp | O tamanho do modelo é a troca entre precisão e velocidade |
| Voz | Kokoro (82M, tem vozes pt-BR), Piper (mais leve) | Testar os dois em português antes de escolher |

## Pontos de atenção

- **Privacidade:** tudo fica num arquivo só, sem criptografia. Quem tiver acesso ao notebook
  tem acesso ao Solis inteiro. Backup é copiar o `solis.db`.
- **Peso em disco:** texto pesa pouco (estimativa de ~20 MB por ano de uso diário). Os
  modelos é que ocupam gigabytes.
- **Qualidade da extração:** um modelo pequeno guarda coisas inúteis e deixa passar fatos.
  O pedido explícito ("grave") existe por isso.

## Como o trabalho acontece

- **No notebook:** Claude Code local. Ele roda o app de verdade contra o Ollama real.
- **Longe do notebook:** Claude Code na nuvem, com o Ollama simulado e testes automáticos.
- **O GitHub é o ponto de encontro:** `git pull` antes de começar, commit e push ao terminar.
