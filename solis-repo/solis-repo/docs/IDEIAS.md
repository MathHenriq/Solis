# IDEIAS — o documento de visão e ideias do Matheus (15/11/2026)

Anotado em 16/11/2026, a pedido do Matheus, do documento dele "Solis — Documento de Visão e
Ideias" (15/11/2026). Ele disse: "fiz este documento com todas as informações que fui pensando;
algumas já temos a teoria, algumas novas".

**Como ler este documento**

- **Quando:** é o mais novo e o mais completo dos documentos de visão. O `VISAO.md` (11/11) e o
  `AGENTES.md` (13/11) continuam valendo onde este não fala do assunto.
- **Onde ele muda o que existe:** a lista está em "O que este documento muda", no fim. São
  decisões do Matheus, não minhas: cada uma está marcada com o que falta ele decidir.
- **Os filtros valem já:** os princípios abaixo são o filtro de toda função nova (o CLAUDE.md
  aponta pra cá). Cada item do plano tem três campos: o problema real que resolve, se o Claude
  Code já faz, e como medir que funciona.
- **Tecnologias e preços:** os que aparecem aqui (openWakeWord, Gemini Live, os preços por
  minuto) são do documento dele, de out–nov/2026. Antes de adotar, conferir de novo e trazer 3
  opções lado a lado (o princípio 8).
- **Faltam duas figuras:** o documento tinha dois desenhos que não vieram no arquivo
  ("arquitetura · IAs, cérebro e corpos" e "ordem de construção · 4 fases, 3 portões"). As fases
  e os portões estão pedidos ao Matheus.
- **O que já existe:** onde o Solis de hoje já cumpre algo, está em "Onde o Solis já está".

O texto abaixo é o do Matheus, organizado. Nada foi tirado.

---

## Visão

O Solis é um sistema pessoal de IA que organiza várias IAs em volta da vida de uma pessoa: ouve,
vê, lembra, age por conta própria quando faz sentido e explica o que faz. Ele não vende IA; vende
a organização das IAs em torno de alguém.

O primeiro usuário é o Matheus. O Solis nasce para resolver problemas reais dele; se ficar bom o
bastante, outras pessoas vão querer usar. Público futuro: quem cria soluções com IA e não domina
todas as ferramentas.

**Regra-mãe: nada de lorota.** O mercado está cheio de "Jarvis" que prometem 200 funções e
entregam 3, com telas de gráficos decorativos. O Solis faz o contrário: poucas funções que
funcionam de verdade, medidas com dados, sem promessa que não se cumpre. Se for para resolver um
problema que não existe, ou que o Claude Code já resolve, não vale o custo.

## Princípios

Toda função nova passa por estes filtros antes de entrar no plano.

1. **Problema real primeiro.** A função nasce de uma situação real, de preferência do Matheus
   (ex.: legenda numa reunião em inglês; sistema da Micro Ka que caiu sem ninguém avisar).
2. **Teste do "o Claude Code já faz?".** Se já faz bem, o Solis integra e usa, não refaz.
3. **Só existe o que funciona.** Função só fica ativa depois de passar num teste de qualidade
   (ex.: 9 acertos em 10).
4. **Taxa de sucesso medida.** O registro de uso mostra, por função, quantas vezes deu certo e
   quantas falhou.
5. **Visual a serviço da informação.** Nenhum gráfico decorativo; todo número na tela é real e
   serve para decidir algo.
6. **Poucas que funcionam valem mais que muitas que fingem.**
7. **Regra do valor.** Grátis por padrão. Pago só se for pelo menos 3x melhor. Caro só se for
   indispensável.
8. **Pesquisa de mercado antes de escolher ferramenta.** Ver o que produtos pagos usam,
   demonstrações reais, comparativos recentes, custo e licença; trazer 3 opções lado a lado.
9. **Sem depender de um fornecedor.** Cada função roda com qualquer IA conectada, inclusive
   grátis, e mostra seus requisitos.
10. **Explica o que faz.** O Solis não só faz; explica por que fez, em linguagem simples.
11. **Divulgação honesta.** Uso real, sem cortes, com limites. Nenhuma promessa de renda.

Cada item do plano tem três campos: problema real que resolve, se o Claude Code já faz, e como
medir que funciona.

## Arquitetura

O Solis não pode depender do PC ligado nem de IA local: o cérebro fica na nuvem e cada aparelho é
um corpo. Isso muda a estrutura atual (tudo no PC com FastAPI local).

*(Aqui o documento tinha o desenho "arquitetura · IAs, cérebro e corpos", que não veio no
arquivo.)*

**Cérebro na nuvem** — um servidor alugado, sempre ligado (algumas dezenas de reais por mês).
Guarda a memória, roda os agentes, o WhatsApp e as tarefas agendadas. A parte valiosa
(orquestração, instruções dos agentes) fica aqui, o que também protege o código.

**Corpos** — app do PC (olhos, ouvidos e mãos: tela, microfone, webcam, controle do computador),
app do celular e acesso por link no navegador.

**Três camadas de execução**

1. **Reflexo, sem IA:** comandos fixos, atalhos, checagens simples (site no ar? conflito de
   agenda?). Custo zero, nunca cai.
2. **Modelo pequeno ou barato:** ouvir (Whisper), classificar pedidos, resumir, anotar memória.
3. **Modelo grande:** pensar, ver a tela, programar, conversar.

IA local só serve para tarefas pequenas (ativação por voz, transcrição). Uma GTX 1650 tem 4 GB de
vídeo, teto de uns 4 bilhões de parâmetros; um modelo de 120 bilhões precisa de 65 a 70 GB.
Modelos abertos grandes são usados pela nuvem (Groq, OpenRouter), não em casa.

**Como o Solis programa** — comanda os agentes de cada empresa (Claude Code pelo Agent SDK, Codex
pela ferramenta da OpenAI), porque cada um é melhor com o próprio modelo. Para o resto (conversa,
agentes da vida, pesquisa), usa um "tradutor universal" que fala com qualquer modelo pelo mesmo
caminho.

**Passagem de bastão** — a continuidade fica no caderno do projeto, não no SDK: código na pasta,
arquivo de plano e registro de progresso. Se a cota do Claude acaba, o Codex lê o plano e o
registro e continua.

**Peças de Lego em vez de 200 funções** — poucas ferramentas universais (mensagem, agenda,
navegador, arquivos, terminal, controle de tela) + conectores prontos via MCP + tarefas
agendadas. A IA combina as peças a partir do pedido em texto. Quando falta uma peça, entra a
autoexpansão: o Solis pede ao Claude Code para criar, testa, pede aprovação e adiciona.

## Personalidades

Cada personalidade é um agente com nicho, jeito de falar e de pensar próprios, e uma área própria
na memória.

| Personalidade | Nicho | Exemplos de uso |
| --- | --- | --- |
| Jarvis | Desenvolvedor e auxiliar técnico | Comanda Claude Code e Codex, explica o que estão fazendo |
| Eva | Carreira (e possivelmente análise de soluções) | Desabafo sobre o trabalho, planos de carreira, ideias de renda |
| Ed | Treino, peso, alimentação | Monta treinos, marca horários, acompanha evolução |
| Assessor | Rotina e finanças | "Anota que gastei X", lembretes, agenda, via WhatsApp |

**Memória por personalidade** — uma memória única, com uma área por personalidade: todos leem,
cada um escreve na sua.

**Inspiração** — em profissões e estilos (ex.: "treinador de fisiculturismo experiente"), nunca em
pessoas reais com nome. O usuário ajusta o tom sem descaracterizar a personalidade.

**Conversa entre personalidades** — quem foi chamado fala. As outras deixam notas laterais
discretas ("Jarvis tem uma observação"), que o usuário abre se quiser. Ninguém interrompe um
desabafo com assunto alheio.

**Três níveis de interrupção**

- Urgente: fala ("posso interromper? às 5h30 você tem reunião")
- Importante: aviso na tela
- Informativo: nota lateral

Quem detecta o conflito é um checador sem IA (comparar horários é conta simples); a personalidade
só dá a voz ao alerta.

**Saúde** — o Solis aponta o que viu e sugere procurar um médico; não receita.

**Custo** — as outras personalidades não ficam pensando o tempo todo: só acordam quando o assunto
toca a área delas, decidido por regra ou modelo baratíssimo.

## Agentes

*Decisão de 17/11/2026: estes agentes e a equipe do `AGENTES.md` viraram uma lista só, atrás das
personalidades (ver "O que este documento muda", item 4, e o `AGENTES.md`).*

Um agente, uma função bem definida. Agentes parados custam zero; só gastam quando agem.

| Agente | O que faz | Onde entra IA |
| --- | --- | --- |
| Pesquisador | Procura novidades de IA, ferramentas e modelos; propõe pelo WhatsApp ou app; com o "sim", escreve o pedido completo e manda ao Claude Code | Pesquisar, resumir, escrever a tarefa |
| Vigia de projetos | A cada 1–2 h confere sites no ar, cotas, erros e segurança | Só para explicar o problema e sugerir correção |
| Segurança | Checa todo projeto antes de publicar (chaves expostas, tabelas sem RLS, portas abertas); atualiza as regras diariamente | Explicar a falha com exemplo real e propor correção |
| Implementação | Antes de construir, faz pesquisa de mercado da melhor ferramenta e traz 3 opções | Pesquisa e comparação |
| Validador de ideias | "Já existe? Tem versão grátis? Como me diferenciar?" | Pesquisa de concorrentes |
| Caixa de ideias | Áudio no WhatsApp vira tarefa, e o Solis já começa | Transcrever e estruturar |

**Travas** — nada é construído sem o "sim" do usuário; tudo é testado à parte antes de entrar;
regra de segurança nova passa por aprovação antes de valer (evita que um texto mal-intencionado
na internet "ensine" o agente).

**Criar agente por texto** — o usuário descreve o agente em linguagem natural, sem montar nós
(sem n8n). Agentes criados viram receitas salvas e compartilháveis.

**Escritório visual** — um lugar para ver cada agente trabalhando: o que está fazendo, onde está
pesquisando. Só mostra atividade real.

## Voz, visão e presença

Voz é a prioridade número 1: hoje o Solis acerta cerca de 5 em cada 10 chamadas e demora para
responder. Nada novo deve entrar antes de isso passar no teste de qualidade.

**Por que a escuta falha** — o Whisper não foi feito para esperar uma palavra de ativação. O certo
são três peças:

1. Detector de ativação treinado só para "Solis" (openWakeWord, grátis e treinável com a voz do
   usuário; ou Porcupine). Roda sempre, quase sem custo.
2. Detector de fala: sabe quando a pessoa começou e terminou de falar.
3. Só então o Whisper transcreve.

Microfone do notebook piora; vale testar com headset para separar as causas.

**Dois modos de voz**

| Modo | Para quê | Como funciona |
| --- | --- | --- |
| Pedido | Chamar o Solis para fazer algo | Cascata contínua: transcrição enquanto fala, IA começa a responder, voz (Fish Audio) fala a primeira frase enquanto o resto é gerado. Narra o que está fazendo ("escolhi o Claude, mandando...") com frases gravadas uma vez e reutilizadas, custo zero |
| Conversa | Bate-papo com as personalidades | Voz em tempo real (Gemini Live ou gpt-realtime mini), minutos inclusos por plano; acabou, volta para a cascata; desliga sozinho após ~30 s de silêncio |

Meta de resposta no modo Pedido: perto de 1 segundo.

**Visual da voz** — a tela escurece levemente e aparece uma esfera animada com cor, forma e voz de
cada personalidade. Ela mostra o estado real (ouvindo, pensando, falando), não é enfeite.

**Webcam sob demanda** — liga só quando chamada ("Solis, olha isso na minha mão"). Uma foto custa
pouco; vídeo contínuo custa muito. Indicador sempre visível quando microfone ou câmera estiverem
ativos.

**Entender sem palavras-chave** — "cheguei, reunião em 20 minutos, resume a ata" funciona com IA +
conectores (Drive, Outlook, agenda) via MCP.

**Legenda ao vivo** — transcreve e traduz reuniões em tempo real (Whisper + tradutor barato), sem
depender da cota da assinatura. Em reuniões de trabalho, conferir a política da empresa sobre
transcrição.

**Controle do PC** — ferramentas universais + controle de tela (a IA vê e clica em qualquer
programa; mais lento e caro, usado quando não há ferramenta específica). Ligar o PC pela rede
(Wake-on-LAN).

## Gerente de IAs e custos

O gerente decide qual IA faz cada tarefa por custo, limite e qualidade, com base em dados do
próprio uso. Gerir cotas e custos é o papel do Matheus como analista de soluções.

**Como decide** — o Solis registra cada tarefa: qual IA fez, se deu certo, quanto custou, quanto
demorou. Com o tempo, sabe qual IA usar para cada coisa dentro do orçamento. O agente Pesquisador
traz modelos novos; o Solis testa e compara.

**Plano B automático** — o Claude bateu o limite, passa para o GPT, depois para um modelo aberto
na Groq ou para o Gemini grátis, e avisa. Funções críticas (como a legenda) nunca dependem de uma
única cota.

**Painel de consumo** — mostra tudo o que está conectado: cota do Claude, cota do GPT, saldo da
OpenRouter e da Groq, gasto do dia e quanto falta para o teto diário. Desde junho de 2026, o uso
do Agent SDK nos planos do Claude sai de um crédito mensal separado do uso interativo; o painel
mostra os dois.

**Ficha de custo por função** — quem roda, quanto custa por uso, qual é a versão grátis ou barata.

**Regras de custo**

- Modelo certo para cada trabalho: preços vão de cerca de US$ 0,10 a US$ 15 por milhão de tokens.
  Memória, resumo e classificação vão para os baratos; conversa principal e código para os bons.
- Resumos no lugar de releitura: a memória guarda versões curtas.
- Personalidades só acordam quando o assunto é delas.
- O que for caro de verdade vira função de plano superior, nunca escondido no básico.

**Provedores sem conta surpresa**

- OpenRouter: crédito pré-pago; acabou, para. Modelos grátis: 50 pedidos/dia, 1.000/dia depois de
  comprar US$ 10.
- Groq: plano grátis sem cartão; no pago, teto mensal configurável (com atraso de 10–15 min na
  contagem).

**Custos de voz em tempo real (por minuto, out/2026)**

| Modelo | Usuário falando | IA falando | 1 hora estimada |
| --- | --- | --- | --- |
| Gemini 3.1 Flash Live | US$ 0,0050 | US$ 0,0180 | ~US$ 0,70 |
| gpt-realtime-2.1-mini | US$ 0,0060 | US$ 0,0240 | ~US$ 0,90 |
| gpt-realtime-2.1 | US$ 0,0192 | US$ 0,0768 | ~US$ 2,90 |

Estimativa com metade do tempo cada um falando, sem texto e sem crescimento do histórico. No
Gemini Live, cada turno cobra o histórico inteiro; conversas longas precisam ser "zeradas" de
tempos em tempos.

## Funções para quem cria soluções com IA

O que o Claude ou o ChatGPT sozinhos não fazem, voltado a quem cria soluções sem dominar todas as
ferramentas.

| Função | O que faz |
| --- | --- |
| Auditoria (nome provisório: Conselho / Mesa Redonda) | As IAs propõem em separado, criticam as propostas umas das outras e o Solis mostra um resumo lado a lado; o usuário escolhe o melhor de cada e isso vira o plano. Mostra o custo antes de rodar |
| Entrevista antes de construir | Algumas perguntas viram a especificação antes de qualquer código |
| Arena | A mesma tarefa para 2–3 IAs, lado a lado, com custo e tempo; os votos alimentam o gerente |
| Previsão de custo | "Essa tarefa deve custar cerca de R$ X com o Claude ou R$ Y com o Gemini" |
| Raio-X do projeto | Abre qualquer pasta e explica, de forma visual e simples, o que cada parte faz |
| Linha do tempo com desfazer | Tudo o que os agentes fizeram, com pontos de volta |
| Guardião antes de publicar | Checagem automática de segurança antes de qualquer site ir ao ar |
| Modo didático | Explica cada peça: o que roda no PC, o que roda na nuvem, quanto custa, por quê; como funcionam agentes e subagentes |
| Selos de requisito | Cada função mostra "roda no seu PC", "precisa de IA na nuvem", "precisa de X GB de vídeo" |
| Conectores externos | O usuário adiciona qualquer API ou conector MCP, mesmo que o Solis não conheça |
| Modo reunião | Legenda, resumo e tarefas extraídas que caem direto no Assessor |

## Segurança, permissões e privacidade

Segurança não dá garantia de 100%, mas reduz muito o risco, e o Solis explica o porquê de cada
proteção.

**Construção segura** — um arquivo de "regras da casa" que toda IA segue ao construir. Base em
listas consagradas (OWASP Top 10). A maior parte da checagem usa verificadores prontos e grátis
(chaves expostas, tabelas sem RLS, portas abertas); IA só para explicar. O problema não é o
Supabase em si, e sim a configuração descuidada.

**Níveis de permissão**

| Nível | Exemplos |
| --- | --- |
| Livre | Abrir, ler, pesquisar |
| Pergunta antes | Enviar, comprar, apagar, publicar |
| Proibido | Senhas, banco |

**Conectores externos** — chaves no cofre de senhas do sistema, nunca em arquivo aberto; cada
conector com permissão limitada.

**Memória total, com bibliotecário** — tudo é salvo e organizado (fatos, pessoas, projetos,
diário, documentos), ligado numa rede de conhecimento. Cada IA recebe só o que importa para a
tarefa, via busca por significado. Guardar é barato; o caro é fazer as IAs lerem tudo.

**Privacidade da memória** — criptografada; o usuário vê, edita e apaga tudo; saúde e finanças
numa área protegida. Para vender, seguir a LGPD.

**Código protegido** — nenhum app instalado é 100% ilegível. A proteção real é a arquitetura: a
parte valiosa fica no servidor; no aparelho, só a interface e as mãos. Mais código embaralhado e
licença de uso.

## Modelo de negócio

Vender vem depois do uso próprio, mas toda função já nasce pensada para não gerar prejuízo por
cliente.

**Restrição importante** — a Anthropic não permite que produtos de terceiros usem o login ou a
cota da assinatura do Claude dos usuários. Para uso pessoal do Matheus, tudo bem; para vender, o
cliente usa chave de API (paga por uso). Conferir a regra equivalente da OpenAI antes de prometer
uso da cota do ChatGPT/Codex.

**Dois caminhos**

| Caminho | Custo de IA | Para quem |
| --- | --- | --- |
| Cliente traz as chaves | Do cliente; o Solis cobra só pelo sistema | Quem já usa APIs |
| IA inclusa | Do Solis, coberto pela assinatura | Leigos; risco fica com o Solis |

**Como nunca pagar para o cliente usar (IA inclusa)**

- Nunca "ilimitado": cada plano tem crédito de IA em reais (ex. ilustrativo: assinatura de R$ 50
  com até R$ 20 de IA).
- Crédito acabou: cai para modelos baratos ou grátis, ou o cliente compra pacote extra.
- Funções caras gastam mais crédito, visível para o cliente.
- Teste grátis com crédito limitado, não com tempo livre.
- Corte automático por usuário.

**Preço vem de dados** — o Matheus é o usuário nº 1; o painel registra o custo real de cada
função. Preço = custo de um usuário pesado + margem.

**Contra a obsolescência** — assinatura + melhoria contínua; o agente Pesquisador é o motor disso.

**Distribuição** — vídeos curtos de uso real e sem cortes; cursos e comunidade (o Matheus já
ensina IA na Clarify). Instalação em até 30 minutos.

**Frase de resultado** — o Solis precisa de uma frase que diga o resultado que entrega, não a
lista de funções (a definir).

## Referências analisadas

Os "Jarvis" do mercado mostram o que impressiona (voz e iniciativa) e o que evitar (funções que
não funcionam, visual decorativo, promessas de renda).

| Referência | O que é | O que aprendemos |
| --- | --- | --- |
| ["Sexta-feira" (kobi.ia)](https://www.instagram.com/reel/Dfvl0gLP0ux/) | Assistente que controla o Windows; usa Groq + Gemini grátis | O cérebro é IA pronta; o trabalho está em voz, ações e memória |
| [Jarvis (lukebuildsai)](https://www.instagram.com/reel/Dfkt52lBqrn/) | Agente que cuidou do negócio por 5 dias, mandou resumos e ligou uma vez | Iniciativa e ligação impressionam; o vídeo é funil de venda |
| [The AI Agency Builder](https://theaiagencybuilder.com/) | Curso grátis + Jarvis montado na Base44; ganha como parceiro da plataforma; aluno paga ~US$ 150 | O custo de IA fica com o cliente; resultado claro vende mais que funções; voz estilo Homem de Ferro fisgou alunos |
| [Meu Assessor (Felipe Titto)](https://www.portalin.com.br/?p=841462) | Assistente de rotina e finanças pelo WhatsApp; 300 mil usuários, R$ 60 milhões em 2025 | Simples e no canal que a pessoa já usa |
| [Jarvis open source (fabianocarvalhojr)](https://www.instagram.com/reel/Da1hTnpBuDh/) | Jarvis básico gerado por prompt; esfera de partículas e painel | O Jarvis básico virou prompt grátis; o Solis precisa ir além. Grande procura no Brasil |
| LLM Council (Andrej Karpathy) | Vários modelos respondem e se avaliam | Base para a Auditoria, que vai além: planejamento com o usuário participando |

## Ordem de construção

O núcleo vem primeiro porque todo o resto depende dele; cada fase só começa quando a anterior
passa no seu portão.

*(Aqui o documento tinha o desenho "ordem de construção · 4 fases, 3 portões", que não veio no
arquivo: as fases e os portões estão pedidos ao Matheus.)*

Tudo o que não está nas fases fica como ideia até responder aos três campos dos princípios:
problema real, se o Claude Code já faz, e como medir.

## Questões em aberto

- [ ] Qual é a frase de resultado do Solis?
- [ ] Eva cuida também de análise de soluções, ou isso vira outra personalidade?
- [ ] Qual servidor usar para o cérebro na nuvem, e quanto custa por mês?
- [ ] Quais partes do que já existe no repositório (MCP, Whisper, Fish Audio, temas) ficam, mudam
      ou saem com a nova arquitetura?
- [ ] A regra da OpenAI permite usar a cota do ChatGPT/Codex dentro do Solis?
- [ ] Qual modelo de voz em tempo real vence num teste real em português (Gemini Live x
      gpt-realtime mini)? *16/11/2026: só o Gemini medido — `gemini-3.8-live` acertou 8 de 8 e
      deu o primeiro som 1,37 s depois do fim da fala (mediana), grátis na faixa grátis. A
      OpenAI ficou de fora por ora (sem faixa grátis). Números em `ESCOPO.md` → o modo Conversa.*
- [ ] Quais são os números reais de custo por função, depois de 1–2 meses de uso medido?
- [ ] Nome definitivo da função Auditoria.
- [ ] Política da Syngenta sobre IA pessoal no notebook da empresa e transcrição de reuniões.

---

## Onde o Solis já está (16/11/2026)

Conferido no código, não de memória.

**Peças de Lego (as ferramentas universais)** — quase todas existem e passaram no uso real:
- arquivos e terminal: com cartão de aprovação (`PARIDADE.md`);
- navegador: Chrome ou Edge, com perfil próprio (`navegador.py`);
- controle de tela: com cartão e o print marcado (`tela.py`);
- agenda, tarefas e lembretes: as ferramentas `mcp__solis__*`;
- tarefas agendadas: `agendadas.py`;
- conectores da conta do claude.ai e servidores MCP próprios: `servidores_mcp.py`.

Falta a "mensagem" (WhatsApp, só pela API oficial da Meta) e a autoexpansão.

**Níveis de permissão** — o "livre / pergunta antes" já é o modelo:
- ler, abrir e pesquisar são livres;
- escrever, rodar comando, clicar, agendar e mudar coisa num conector pedem cartão.

O "proibido" existe em partes: o Claude é instruído a nunca digitar senha, cartão ou documento,
`browser_run_code_unsafe` fica fora, e nada cai na janela do Solis. Não há ainda uma lista
"proibido" configurável.

**Plano B automático** — o roteador já passa de um cérebro pro próximo quando um falha ou a cota
acaba (`roteador.py`: a ordem escolhida em Configurações → Cérebros, com Claude, Codex, local,
Groq, Gemini, Mistral, OpenRouter). Falta o "e avisa" ficar claro na tela, e a decisão por dados
(o gerente).

**Registro de uso** — `banco.registrar_acao` guarda o que o Solis fez no computador (90 dias), e
as etapas de cada resposta ficam no banco (qual cérebro, tempos). Desde 17/11/2026 há também o
registro de uso (`banco.usos`, `qualidade.py`): cada vez que um cérebro responde ou falha (inclusive
quando ninguém responde) e cada ferramenta usada, com o voto do Matheus (👍/👎) na resposta. Fica
mesmo com a conversa apagada. A taxa por função aparece em Configurações → Taxa de acerto.

**Painel de consumo** — começou: Configurações → Uso mostra a cota do Claude (sessão de 5 h, a
semana, o Fable) pelo `/usage` do CLI. Falta o resto:
- a cota do GPT e os saldos da OpenRouter e da Groq;
- o gasto do dia e o teto diário;
- o "crédito separado do Agent SDK desde junho de 2026": o `/usage` de 15/11 diz "you are
  currently using your subscription to power your Claude Code usage". Conferir na documentação
  antes de mostrar dois números.

**Voz** — a escuta usa o Whisper pra achar a palavra "Solis" (`ativacao.py`). O Porcupine ficou
sem uso: a conta virou só pra empresas. O openWakeWord já estava anotado como o próximo, com um
modelo treinado fora (o PyTorch é bloqueado pelo Controle de Aplicativo do PC). Isto bate com o
diagnóstico do documento. A fala usa uma cadeia: Gemini TTS, depois a Ava do Edge, depois a voz
local. A Fish Audio está em teste na frente quando há chave (`fala.py`).

**Chaves e privacidade** — as chaves dos cérebros (Groq, Gemini…) ficam no cofre do Windows
(DPAPI, `cofre.py`), e a memória privada também é criptografada. As variáveis (chaves de API)
dos servidores MCP também, desde 17/11/2026 (ver o item 5 abaixo). Uma exceção, aberta: o índice
de busca guarda o texto legível da memória privada (anotado em `banco.py`).

**Memória** — a busca por significado e a memória visível em Conhecimento existem (`busca.py`,
o grafo). Falta a área por personalidade.

**Agentes** — os ajudantes (subagentes) do Claude aparecem trabalhando na barra do projeto, com o
que fazem agora. É o embrião do escritório visual. Os agentes deste documento (Pesquisador,
Vigia, Segurança…) e os do `AGENTES.md` (Manager, Atlas, Nexus, Athena, Sentinel) ainda não
existem.

## O que este documento muda — esperando a decisão do Matheus

1. **A arquitetura: do "local primeiro" pro "cérebro na nuvem".** O `VISAO.md` (11/11) ainda diz
   "local primeiro, nuvem quando ajuda", e o Solis de hoje roda inteiro no PC (FastAPI local). Este
   documento põe o cérebro num servidor alugado e o PC como um dos corpos. É a maior mudança: mexe
   em memória, agentes, tarefas agendadas e no próprio jeito do app falar com o servidor. Falta
   decidir o servidor, o custo e o que fica, muda ou sai (está nas questões em aberto).
2. **A ordem: voz antes de qualquer coisa nova.** O documento diz que nada novo entra antes de a
   voz passar no teste de qualidade (hoje ~5 em 10). O trabalho dos últimos dias seguiu a ordem
   do `PARIDADE.md` (navegador, agendadas, skills, MCP, estilos, uso, tela). Pelo documento, o
   próximo passo deixa de ser os hooks e passa a ser a voz: as três peças da escuta, medidas com
   uma meta (ex.: 9 em 10) e a resposta perto de 1 s.
3. **Os hooks — decidido e feito (17/11/2026): o Matheus escolheu fazer a tela** (Configurações →
   Hooks, gravando na configuração do Claude Code). O que estava proposto, pra registro: o
   princípio 2. O Claude Code já faz hooks, e o Claude do Solis já carrega a
   configuração de usuário do Claude Code (`setting_sources` "user"): os hooks que o Matheus
   puser lá já valem. Pelo princípio "o Claude Code já faz? integra, não refaz", a tela de hooks
   no Solis sairia do plano até aparecer um problema real.
4. **Personalidades e agentes — decidido (17/11/2026): duas camadas.** As personalidades (Jarvis,
   Eva, Ed, Assessor) são com quem o Matheus fala; os agentes são quem trabalha atrás delas, e as
   duas listas de agentes (a deste documento e a equipe do `AGENTES.md`) viram uma só. Ele pede ao
   Jarvis, e o Jarvis chama os agentes. Os agentes têm os dois nomes, o próprio e o cargo ("Atlas ·
   Pesquisador"), que aparecem juntos nos modelos 3D do escritório. A lista unida está no
   `AGENTES.md`, seção "Decisão de 17/11/2026". Nada foi construído: é a direção pra quando a
   frente começar.
5. **Chaves dos servidores MCP no cofre — decidido e feito (17/11/2026).** O Matheus escolheu o
   cofre com um lançador, em vez de "só pelo Solis": as variáveis ficam no cofre do Solis, e nos
   arquivos do Claude Code e do Codex vai só `python -m solis.lancar_mcp <nome> <comando>`, que abre
   o cofre na hora de ligar o servidor. O custo que a proposta tinha (o servidor deixar de valer no
   terminal) sumiu: vale no Claude Code e no Codex do terminal, na mesma conta do Windows, com o
   Solis instalado (não precisa estar aberto).
6. **Taxa de sucesso por função e "só existe o que funciona" — decidido e feito (17/11/2026).** O Matheus escolheu medir as duas coisas: se a função **rodou** (o que o Solis
   sabe sozinho: o cérebro respondeu ou falhou, a ferramenta deu certo ou erro) e se ela
   **acertou** (o voto dele, 👍/👎, opcional, embaixo da resposta). E o "só existe o que funciona"
   mostra, não desliga: cada função aparece como passou, não passou ou sem teste, e os testes com
   meta entram um por um. Feito: o registro e o voto no servidor, e o voto na tela (aprovado pelos prints,
   `design/voto-validacao.png`). A tela da taxa, em Configurações → Taxa de acerto: aprovada pelos
   prints (`design/qualidade-validacao.png`). Próximo passo da regra: um teste com meta pra cada
   função que ainda não tem. Uma ferramenta recusada no cartão não conta
   como falha dela (visto no histórico real: as duas falhas de "Write" eram recusas).
