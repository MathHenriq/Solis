# Escopo do Solis — onde estamos e para onde vamos

Documento vivo. Atualizar ao fechar cada fase. Última revisão: 30 de outubro de 2026.

## A visão

Um assistente pessoal que conhece o Matheus por inteiro: tudo o que ele manda é guardado,
tudo o que ele diz é entendido no contexto da vida dele, e o histórico é completo. A
referência é o Jarvis: prontidão, voz, acesso total ao computador.

O Solis tem **dois papéis**, e separar os dois resolve quase tudo:

1. **Ser a memória.** Tudo sobre o Matheus mora no Solis, na máquina dele. É a fonte da
   verdade — inclusive pros outros assistentes.
2. **Executar.** Responder, pesquisar, programar, controlar o PC. A inteligência vem de onde
   for melhor no momento: Claude Code e Codex (pela assinatura do Matheus, nunca API paga),
   APIs gratuitas, ou modelos locais quando a cota acabar ou o assunto for privado.

**O que isso entrega e o que não entrega.** A vantagem do Solis é o **contexto**: ele sabe
da Syngenta, dos estudos, das preferências, sem que nada precise ser repetido. Um modelo
local de 3B a 14B **não** raciocina como um modelo de nuvem de ponta — por isso o trabalho
pesado (código, sistemas grandes como a NF-e da loja) vai pros modelos de nuvem, e o Solis
entrega a eles o contexto certo.

## Decisões do Matheus

| Questão | Decisão |
|---|---|
| Prioridade | Um assistente que guarda e lembra de tudo. Sem ordem fixa além disso |
| Servidor | O PC de casa liga quando for usar; o notebook é a reserva, acordado por Wake-on-LAN |
| Privacidade | Modo privado: senhas, saúde e o que for marcado nunca saem da máquina. O resto pode ir pros modelos de nuvem |
| Tecnologias | Nenhum apego. Escolher medindo |
| Hardware | Notebook com 8 GB de VRAM (o principal). PC de casa com GTX 1650 de 4 GB |

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
| Busca por significado | Memórias e mensagens viram vetores; cada pedido leva as memórias e os trechos de conversas antigas mais parecidos com a mensagem |
| Modo privado | Memórias sensíveis são marcadas — pelo modelo, ou à força quando a mensagem diz "privado" |
| Memória que muda | Fato novo que desmente um antigo o substitui; o antigo fica guardado, fora da tela |
| Conversa longa | O começo vira resumo; as 20 últimas mensagens vão inteiras |
| Cérebros | Claude Code e Codex respondem pelo Solis com a assinatura; o modelo local é a reserva e o guardião do que é privado |
| MCP | O Claude Code e o Codex consultam a memória do Solis mesmo fora dele |
| Importação | O histórico do ChatGPT e do Claude entra na busca e na memória |
| Prompt honesto | O prompt de sistema diz o que o Solis **não** consegue fazer, pra ele não inventar |
| Erros | Cada falha diz quem falhou: servidor, Ollama ou falta de modelo |

73 testes automáticos no servidor, rodando sem precisar do Ollama.

### O que ainda é provisório

- Tarefas, Agenda, Conhecimento e Ferramentas mostram dados de exemplo.
- O piso de similaridade da busca foi escolhido sem dados reais; precisa calibrar no notebook.
- A memória privada está em texto puro no `solis.db` (sem criptografia).
- O servidor precisa ser ligado à mão (`npm run backend`).
- Não há controle na tela pra esquecer uma memória nem pra voltar a conversas antigas.

## Para onde vamos

A regra: **primeiro o que torna o Solis útil, depois o que o torna impressionante.** Voz
sobre um assistente que esquece as coisas é só um assistente que esquece as coisas,
falando. As fases não têm ordem rígida (decisão do Matheus), mas as primeiras são a base
das outras.

### Memória completa — em andamento

- [x] Conversas guardadas; memória automática e pedida.
- [x] Busca por significado em memórias e conversas antigas (RAG).
- [x] Conversa longa: o começo vira resumo, o fim vai inteiro, sem buraco entre os dois.
- [x] Marca de privada.
- [x] Contradição: "saí da Syngenta" substitui a memória antiga (que fica guardada, marcada).
- [ ] Esquecer e corrigir memória pela tela; lista de conversas antigas (precisam de referência visual).
- [ ] Busca textual (FTS5) na tela de Memória.
- [ ] Criptografar as memórias privadas (DPAPI do Windows).

### Importar o passado — pronto, falta conferir com os arquivos reais

- [x] Importador do ChatGPT e do Claude (`python -m solis.importar`), sem duplicar ao repetir.
- [x] Conversas importadas entram na busca, com o autor certo ("ChatGPT disse").
- [x] Memórias tiradas do histórico, retomáveis, com data, sem substituir o presente.
- [ ] Conferir o leitor do Claude com uma exportação real (os campos não foram confirmados).

### Cérebros externos — pronto, falta conferir o Codex no notebook

- [x] Claude Code e Codex pelo CLI oficial, com a assinatura (`/claude`, `/codex`, `/local`).
- [x] Roteador por regras, com a preferência pelos mais fortes e queda pro próximo.
- [x] Nada privado vai pra nuvem; extração, vetores e resumo sempre locais.
- [x] Servidor MCP de memória, testado com o Claude Code de verdade.
- [ ] Conferir o Codex rodando de verdade (integrado só pela documentação).
- [ ] APIs gratuitas (Gemini e outras) como mais cérebros.
- [ ] Escolher a ordem dos cérebros pela tela (hoje é a variável `SOLIS_CEREBROS`).

### Servidor em casa e acesso de fora

- O PC de casa roda o servidor, o banco, os embeddings e um modelo pequeno (cabe na 1650).
- O notebook entra com os modelos maiores quando estiver ligado.
- **Tailscale** liga os aparelhos do Matheus numa rede privada: o Solis é acessado do
  celular ou de outro PC sem nada exposto na internet.
- Wake-on-LAN: funciona bem por cabo, mal ou nada por Wi-Fi, e precisa de algo acordado na
  rede de casa pra mandar o sinal. Se tudo estiver desligado, nada acorda nada.
- Dividir um modelo só entre as duas placas pela rede existe, mas a rede vira gargalo: cada
  máquina com um papel compensa mais.

### Conhecimento: os seus arquivos

A tela Conhecimento indexa PDFs, notas e textos: cada arquivo é cortado em trechos, cada
trecho vira vetor, e entra na mesma busca das memórias.

### Voz

1. **Apertar pra falar** primeiro.
2. **Palavra de ativação** ("Solis") depois.
3. **Camada 3 da assinatura**: o glow do símbolo reagindo ao áudio.

### Controle do PC e visão da tela

- Um agente leve em cada máquina que o Solis controla: arquivos, comandos, programas,
  navegador.
- Permissão por nível: ler é livre; escrever e executar pedem confirmação ou estão numa
  lista aprovada; tudo fica registrado. Motivo técnico: com acesso total e lendo páginas e
  e-mails, um texto malicioso pode mandar o Solis executar coisas (prompt injection).
- Visão sem gastar GPU: a tela é capturada continuamente só na RAM (últimos segundos), junto
  com o título da janela e o texto da interface pela acessibilidade do Windows. O modelo de
  visão só roda quando o Matheus pergunta. Capturas nunca vão pro disco.

### Laboratório de modelos

As mesmas perguntas em vários modelos, com resposta, tempo e nota guardados no SQLite. Serve
pra escolher modelos medindo — e é um projeto de análise de dados com dados reais.

### App de verdade e celular

- O Tauri sobe o servidor sozinho; instalador `.msi`; inicia com o Windows.
- Telegram como canal pelo celular (bot oficial e gratuito). WhatsApp só pela API oficial
  da Meta; as bibliotecas não oficiais violam os termos e podem banir o número.

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

**Orçamento de 8 GB de VRAM.** Whisper, LLM e voz disputam a mesma memória. Modelo que não
cabe inteiro vai em parte pra RAM (offload) e fica várias vezes mais lento:

| Modelo | Tamanho | Cabe inteiro em 8 GB? |
|---|---|---|
| qwen3:8b | 5,2 GB | Sim, com folga |
| qwen3.5:9b | 6,6 GB | Sim, com pouca folga |
| gemma3:12b | 8,1 GB | Não |
| qwen3:14b | 9,3 GB | Não |

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
