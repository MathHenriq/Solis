# PLANO — tudo o que o Solis ainda vai ter

Pedido do Matheus (10/11/2026): "criar TUDO primeiro, e aí ir às funções uma a uma, passo a passo".
Este é o mapa do tudo. O `ESCOPO.md` continua sendo o registro do que já foi feito e medido; aqui
fica o que falta, em blocos, com a ordem proposta e o que cada bloco precisa pra começar.

Lembrete do fluxo (CLAUDE.md): construir pode ser em paralelo no código, mas **aprovar é uma tela por
vez** — cada peça visível vai pros prints (3 temas × 2 navegações) antes de ser dada como pronta.

Legenda: ✅ feito · 🟡 em andamento · ⬜ não começou · 🔒 depende de uma decisão do Matheus

---

## 1. O Solis na tela — o app de verdade

| | O quê | Precisa |
|---|---|---|
| 🔒 | **App Tauri compilado** (hoje é uma aba do navegador em localhost) | Instalar Rust + Build Tools do Visual Studio (~3 a 6 GB). E conferir o Controle Inteligente de Aplicativos: um .exe compilado aqui não é assinado, e o SAC pode bloquear — já bloqueou o PyTorch. |
| ⬜ | **Aparecer quando chamado**: "Solis" → uma janela pequena, sem moldura, transparente e por cima de tudo, no centro de baixo da tela, com o símbolo animado; ele ouve, pensa e responde ali mesmo; um clique abre o app inteiro | App Tauri (janela `overlay` com `alwaysOnTop`, `transparent`, `decorations: false`) |
| 🟡 | **Animação de chamada**: o sol nasce da linha do horizonte, os anéis se abrem e passam a seguir a voz (camada 3); pensando, os anéis recolhem e o brilho respira devagar; respondendo, o brilho acompanha a fala; no fim, o sol se põe | Nada — desenho próprio, feito primeiro no app web e reaproveitado na janela do Tauri |
| ⬜ | Servidor sobe junto com o app (sidecar), ícone na bandeja, inicia com o Windows, instalador `.msi` | App Tauri |
| ⬜ | Atalho de teclado global pra chamar (além da voz) | App Tauri (`global-shortcut`) |

## 2. Ferramentas — no mínimo as do Claude Code / Desktop / Cowork, e além

Regra que vale pra todas (ESCOPO → Controle do PC): **só o modelo local mexe no PC**; ler é livre
nas pastas autorizadas; escrever e executar pedem confirmação (ou estão numa lista aprovada); o que
vem de arquivo, página ou e-mail é informação, nunca ordem; tudo fica no registro.

| | Ferramenta | Equivalente | Nível |
|---|---|---|---|
| 🟡 | Listar pasta, buscar arquivo (nome e conteúdo), ler arquivo (texto, PDF, código) | Read, Glob, Grep | ler |
| ⬜ | Ler Word, Excel, PowerPoint, imagens (visão local) | Read (multimodal), skills docx/xlsx/pptx | ler |
| ⬜ | Criar e editar arquivo (com o diff na conversa antes de aprovar) | Write, Edit, MultiEdit | escrever |
| ⬜ | Mover, renomear, copiar; apagar sempre pra Lixeira | — | escrever |
| ⬜ | Criar documentos: .docx, .xlsx, .pptx, PDF, a partir da conversa | skills do Cowork | escrever |
| ⬜ | Terminal: PowerShell, com saída ao vivo, rodar em segundo plano e acompanhar | Bash/PowerShell, background, Monitor | executar |
| ⬜ | Abrir programas, arquivos e pastas; trazer janela pra frente | computer use (parte) | executar |
| ⬜ | Navegador: abrir página, ler o texto, clicar, preencher (com confirmação) | WebFetch, Claude in Chrome | ler / executar |
| ⬜ | Pesquisa na web (busca + leitura das páginas, com fontes) | WebSearch, deep research | ler |
| ⬜ | Controle do PC por tela: ver, clicar, digitar | computer use | executar |
| ⬜ | Lista de tarefas do próprio trabalho (o plano que ele mostra enquanto faz) | TodoWrite / task list | — |
| ⬜ | Subagentes: dividir um trabalho grande em partes paralelas | Task / Agent | — |
| ⬜ | Tarefas agendadas e recorrentes ("toda segunda às 8h, me resume os e-mails") | scheduled tasks, cron | — |
| ⬜ | Conectores: Gmail, Google Agenda, Drive, GitHub (por MCP) | MCP / conectores | ler / escrever |
| ⬜ | Git: status, diff, commit (com confirmação) | Bash + git | escrever |
| ⬜ | Rodar código Python num ambiente isolado (contas, gráficos, planilhas) | code execution | executar |
| ⬜ | Habilidades (skills): roteiros prontos que o Matheus escreve uma vez | Skills, slash commands | — |
| ✅ | Memória, tarefas, agenda, avisos, conhecimento (arquivos e páginas), voz | memory, Cowork | — |

**Além do Claude:**

| | Ferramenta | Como |
|---|---|---|
| ⬜ | **Legendas ao vivo** do que o Matheus está vendo ou ouvindo: o áudio do PC (vídeo, chamada, jogo) transcrito pelo Whisper e mostrado numa faixa por cima de tudo, com tradução opcional | Captura do áudio do sistema (WASAPI loopback), Whisper em pedaços curtos, janela de legenda do Tauri |
| ⬜ | **Visão da tela**: "o que é isso?", "lê esse erro pra mim" — a tela só na memória, o título da janela e o texto da interface pela acessibilidade do Windows; o modelo de visão só roda quando pedir | Captura da tela + UI Automation + qwen3.5:9b (visão) |
| ⬜ | **Memória da tela**: "o que eu estava lendo ontem à tarde sobre X?" — só o texto (nunca a imagem), com o mesmo cuidado de privado | UI Automation + índice |
| ⬜ | Modo jogo: o Solis solta a GPU quando um jogo abre e avisa que vai responder mais devagar | Lista de processos + Ollama `keep_alive` |
| ⬜ | Agente em outras máquinas (notebook, servidor) controladas pelo mesmo Solis | Agente leve + conexão segura |
| ⬜ | Celular pelo Telegram (bot oficial) | API do Telegram |

## 3. Telas que ainda são de exemplo

| | Tela | O que falta |
|---|---|---|
| ⬜ | Ferramentas | Estado real de cada ferramenta, as pastas autorizadas, o registro do que foi feito |
| ⬜ | Cartão de confirmação na conversa | Aprovar / Recusar / Sempre aprovar isto, com o que vai acontecer (o diff, o comando) |
| ⬜ | Janela de chamada (overlay) e faixa de legendas | Desenho próprio, com o Claude como base |

## 4. Ordem proposta

1. **Sem modelo rodando (agora):** este plano; a animação de chamada no app web; as ferramentas de
   arquivo ligadas na conversa (com Ollama simulado nos testes); a tela Ferramentas real.
2. **Teste de uma vez com os modelos (amanhã):** medir as ferramentas de arquivo de novo, a palavra
   de ativação com a voz real, calibrar o brilho.
3. **App Tauri** (depois da decisão do Rust/SAC): janela de chamada por cima de tudo, bandeja,
   servidor junto, atalho global.
4. Escrever e executar com confirmação → navegador e web → visão da tela → legendas ao vivo →
   conectores e tarefas agendadas → o resto da tabela.
