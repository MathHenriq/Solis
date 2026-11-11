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
| ✅ | **App Tauri compilado** — em desenvolvimento (`scripts/app-dev.ps1`) | Rust e Build Tools instalados (10/11/2026). O Controle Inteligente de Aplicativos barrava o build (os error 4551); o Matheus desligou (11/11/2026). Falta o instalador `.msi`. |
| ✅ | **Aparecer quando chamado**: a ilha preta desce no alto da tela, por cima de tudo | Janela `chamada` (transparente, sem moldura, por cima de tudo, fora da barra de tarefas), testada no app em 11/11/2026 com uma chamada de ensaio (`__ensaioChamada`, só em desenvolvimento). Falta: com a voz de verdade; um clique na ilha abrir o app. |
| 🟡 | **Animação de chamada**: a lógica da ilha do iPhone (pedido do Matheus) — a cápsula desce e abre com mola ouvindo, vira pílula pensando, abre larga respondendo, recolhe e sobe | Feita no app web, PROVISÓRIA (`design/chamada-validacao.png`) |
| ⬜ | Servidor sobe junto com o app (sidecar), ícone na bandeja, inicia com o Windows, instalador `.msi` | App Tauri |
| ⬜ | Atalho de teclado global pra chamar (além da voz) | App Tauri (`global-shortcut`) |

## 2. Ferramentas — no mínimo as do Claude Code / Desktop / Cowork, e além

Regra que vale pra todas (ESCOPO → Controle do PC): **só o modelo local mexe no PC**; ler é livre
nas pastas autorizadas; escrever e executar pedem confirmação (ou estão numa lista aprovada); o que
vem de arquivo, página ou e-mail é informação, nunca ordem; tudo fica no registro.

| | Ferramenta | Equivalente | Nível |
|---|---|---|---|
| 🟡 | Listar pasta, buscar arquivo (nome e conteúdo), ler arquivo (texto, PDF, código) — ligadas na conversa do modelo local, com a etapa na tela e o registro; falta medir com o modelo e a tela Ferramentas | Read, Glob, Grep | ler |
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
| ⬜ | **Modo sem placa** (decisão do Matheus, 11/11/2026: "vão ter momentos que eu vou querer usar o Solis sem usar nada da minha placa"): um interruptor que tira tudo da GPU — o modelo local e a voz descarregam, o Whisper vai pra CPU, o básico segue em código (`rapidas.py`), o resto vai pra nuvem, e a resposta chega num aviso do Windows em vez de falada. Inclui o modo jogo (ligar sozinho quando um jogo abre) | Ollama `keep_alive: 0`, Whisper `cpu`, avisos.py |
| ⬜ | **Resposta por aviso**: chamou "Solis" com a voz desligada, a resposta vem num aviso do Windows ("Anotado: beber água, te aviso às 10h58") — a voz é opcional, ligada quando ele quiser | avisos.py, a escuta |
| ⬜ | Agente em outras máquinas (notebook, servidor) controladas pelo mesmo Solis | Agente leve + conexão segura |
| ⬜ | Celular pelo Telegram (bot oficial) | API do Telegram |
| ⬜ | **O "Meu Assessor" dentro do Solis** (pedido do Matheus, 11/11/2026; a descobrir em detalhe usando o de verdade): o assistente do WhatsApp do Felipe Titto, com 300 mil usuários (segundo a empresa). Pelo que se acha público: pedidos por texto ou áudio no WhatsApp, sem abrir outro app; registrar gastos e receitas e consultar as finanças; compromissos, lembretes e avisos na hora; cobranças, links de pagamento e notas fiscais. No Solis: um módulo de finanças (gastos por mensagem, áudio ou foto do comprovante), e o WhatsApp como canal — só pela API oficial da Meta (as bibliotecas não oficiais violam os termos e podem banir o número) | WhatsApp Cloud API; finanças no SQLite |

## 3. Telas que ainda são de exemplo

| | Tela | O que falta |
|---|---|---|
| ⬜ | Ferramentas | Estado real de cada ferramenta, as pastas autorizadas, o registro do que foi feito |
| ⬜ | Cartão de confirmação na conversa | Aprovar / Recusar / Sempre aprovar isto, com o que vai acontecer (o diff, o comando) |
| ⬜ | Janela de chamada (overlay) e faixa de legendas | Desenho próprio, com o Claude como base |

## Voz na GPU — descartada por enquanto (11/11/2026)

Medido: o Chatterbox Multilingual na GPU gera mais devagar que a fala (~1,2 s de geração por
segundo de áudio) e ocupa 3,6 GB — com o modelo de conversa (5,2 GB) e o Whisper turbo (~1 GB),
passa dos 8 GB da placa. Decisão do Matheus: a voz não é o foco, e o Solis não pode "matar a
placa". Fica a voz de nuvem (Gemini; Ava de reserva) quando ele quiser a voz ligada, e a resposta
por aviso quando não. O ambiente `backend/.venv-voz` (PyTorch + Chatterbox) pode ser apagado.

## 4. Ordem proposta

1. **Sem modelo rodando (agora):** este plano; a animação de chamada no app web; as ferramentas de
   arquivo ligadas na conversa (com Ollama simulado nos testes); a tela Ferramentas real.
2. **Teste de uma vez com os modelos (amanhã):** medir as ferramentas de arquivo de novo, a palavra
   de ativação com a voz real, calibrar o brilho.
3. **App Tauri** (depois da decisão do Rust/SAC): janela de chamada por cima de tudo, bandeja,
   servidor junto, atalho global.
4. Escrever e executar com confirmação → navegador e web → visão da tela → legendas ao vivo →
   conectores e tarefas agendadas → o resto da tabela.
