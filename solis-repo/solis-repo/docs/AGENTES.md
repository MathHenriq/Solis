# AGENTES — visão, arquitetura e requisitos da equipe de agentes do Solis

Anotado em 13/11/2026, a pedido do Matheus, de uma conversa dele com o GPT (documento de
08/11/2026, versão 1.0). Ele disse: "isso fará parte do Solis".

**Como ler este documento**

- **Quando:** é visão futura, pra quando o Solis abrir a aba só de agentes e conhecimento. Não
  passa na frente do que está em andamento: o primeiro marco continua sendo a paridade com o
  Claude (`PARIDADE.md`).
- **O que importa:** o comportamento, os papéis e as regras de autonomia.
- **Tecnologias:** as que aparecem aqui (PixiJS, LangGraph etc.) são propostas discutidas, não
  decisões. Antes de adotar qualquer uma, ver o que o Solis já tem e o benefício real, e
  perguntar ao Matheus.
- **Nomes:** os dos agentes são provisórios.
- **O que já existe:** onde o Solis de hoje já cumpre algo, isso está anotado em "Onde o Solis
  já está", no fim.

O texto abaixo é o do Matheus, organizado. Nada foi tirado.

---

## 1. Visão do produto

O Solis será uma inteligência artificial pessoal, com memória persistente, personalidade
própria, capacidade de usar diferentes modelos de IA e uma estrutura de agentes especializados.

O objetivo não é criar um novo Claude, GPT ou Gemini do zero. É construir uma plataforma que
combine diferentes modelos, ferramentas, memórias e agentes numa experiência de inteligência
pessoal integrada.

O Solis deve evoluir pra ser capaz de:

- conhecer o usuário e compreender as preferências dele;
- aprender continuamente com interações e correções;
- usar modelos locais e externos;
- coordenar vários agentes especializados;
- executar tarefas complexas de maneira autônoma;
- pesquisar oportunidades e novas tecnologias;
- desenvolver protótipos e ferramentas;
- comparar ideias vindas de diferentes modelos;
- apresentar recomendações fundamentadas;
- pedir aprovação humana antes de mudanças importantes.

**Princípio fundamental:** o Solis trabalha ao lado do usuário, não apenas responde às perguntas.

## 2. Inteligência pessoal — o Solis do Matheus

Uma das principais ambições é uma inteligência personalizada. A ideia é trabalhar no futuro com
um modelo local, inicialmente da família Qwen: o "Qwen do Matheus". Em etapas:

**2.1 Memória persistente.** Guardar o que é relevante sobre o usuário, os projetos, as
preferências, as decisões e as experiências.

**2.2 Aprendizado de comportamento.** Aprender com correções e feedback, por exemplo:

- o usuário prefere respostas mais objetivas;
- valoriza ideias inovadoras;
- prefere propostas acompanhadas de evidências;
- pode rejeitar soluções complexas demais.

Essas preferências devem influenciar as respostas futuras.

**2.3 Personalização do modelo.** No futuro, avaliar fine-tuning de modelos locais com exemplos
selecionados e dados apropriados.

> Memória, personalização de comportamento e treinamento de modelo são mecanismos diferentes.
> **Não começar pelo fine-tuning:** primeiro consolidar memória e avaliações.

## 3. Arquitetura multiagente — Solis Agent Office

O Solis terá uma equipe de agentes especializados.

**Execução híbrida:**

- modelos locais;
- APIs externas;
- provedores diferentes de inteligência.

**Autonomia mista:**

- agentes executam tarefas autorizadas sem intervenção constante;
- podem pesquisar, investigar, planejar e experimentar em ambientes controlados;
- precisam pedir autorização pra ações importantes.

A representação visual será um escritório isométrico.

### 3.1 A primeira equipe (nomes provisórios)

| Agente | Papel | O que faz |
|---|---|---|
| **Solis Manager** | orquestrador principal | interpreta objetivos, divide tarefas, escolhe agentes, acompanha execuções, consolida resultados, pede aprovações |
| **Atlas** | pesquisa | pesquisa informações, investiga tecnologias, busca referências, identifica oportunidades, produz relatórios |
| **Nexus** | desenvolvimento | analisa arquiteturas, desenvolve ferramentas, trabalha com código, cria protótipos, roda testes |
| **Athena** | documentação | analisa documentos, organiza informações, extrai conteúdos, produz documentação |
| **Sentinel** | qualidade | valida resultados, identifica inconsistências, revisa implementações, verifica as entregas dos outros |

### 3.2 Princípio de funcionamento

Um agente é uma **identidade especializada**, não necessariamente um modelo independente. Cada
agente tem:

- identidade;
- instruções;
- especialidades;
- ferramentas autorizadas;
- modelo preferido;
- memória ou contexto apropriado;
- permissões;
- histórico de execuções.

Um agente pode fazer tarefas diferentes ao longo do tempo. Não é preciso manter todos os agentes
gastando tokens o tempo todo.

## 4. Agent Office — o escritório virtual

Uma área nova no app, que mostra o ambiente de trabalho dos agentes.

**4.1 Estética.** Isométrica, com:

- salas;
- departamentos;
- estações de trabalho;
- computadores;
- personagens;
- animações;
- áreas de descanso;
- salas de reunião.

Departamentos iniciais:

1. Diretoria.
2. Pesquisa.
3. Desenvolvimento.
4. Documentação.
5. Qualidade.

**4.2 Estados dos agentes.** Os personagens refletem estados **reais** do servidor:

| Estado | O que é |
|---|---|
| Idle | disponível ou descansando |
| Assigned | recebeu uma tarefa |
| Working | executando |
| Waiting | esperando dependências |
| Approval | esperando autorização |
| Completed | tarefa concluída |
| Error | encontrou falha |

Também vai haver estados pra cancelamento, recuperação e novas tentativas.

> **Não usar animações ou indicadores que simulem atividade que não existe.** (O mesmo princípio
> do glow reativo do Solis: estado real, nunca encenação.)

**4.3 Perfil individual.** Ao selecionar um personagem, ver:

- nome;
- especialidade;
- modelo usado;
- tarefas atuais;
- histórico;
- ferramentas disponíveis;
- consumo de tokens e custos;
- memórias e conhecimentos;
- colaborações com outros agentes.

## 5. Solis Council — inteligência colaborativa entre modelos

Uma das funcionalidades mais importantes. O Solis consulta diferentes modelos pra resolver
problemas complexos. Provedores considerados:

- Anthropic / Claude;
- OpenAI / GPT;
- Google / Gemini;
- modelos locais via Ollama;
- outros no futuro, como o Kimi.

**5.1 Análise independente.** Diante de uma ideia ou problema, o Solis manda a mesma pergunta pra
modelos diferentes, e cada um analisa sozinho.

**5.2 Debate entre modelos.** Depois, os modelos avaliam as respostas uns dos outros. Devem
conseguir:

- questionar propostas;
- apontar falhas;
- identificar contradições;
- trazer alternativas;
- defender argumentos;
- incorporar ideias dos outros;
- revisar as próprias recomendações.

O objetivo é uma proposta tecnicamente consistente, não uma votação.

**5.3 Rodadas de consenso.** O debate pode ter várias rodadas, com três resultados possíveis:

- **Consenso:** chegaram a uma proposta bem fundamentada.
- **Consenso parcial:** concordam na direção geral, mas ainda há divergências.
- **Sem consenso:** há divergências relevantes, que vão pro usuário.

Não forçar concordância artificial. Ter limite de rodadas, orçamento de tokens e critério de
encerramento.

**5.4 Síntese do Solis.** O Solis consolida:

- as ideias que convergem;
- as ideias exclusivas de cada modelo;
- as divergências;
- os argumentos;
- as evidências e fontes;
- os riscos;
- as alternativas;
- a recomendação final.

**5.5 Autoridade do usuário.** Consenso dos modelos não é autorização pra executar. Decisões
estratégicas, financeiras, de segurança e mudanças importantes no produto vão pro usuário, que
aprova, rejeita ou pede mais rodadas.

**5.6 Dois modos:**

- **Independente:** cada modelo analisa, o Solis faz a síntese.
- **Debate:** os modelos discutem até chegar a consenso, ou até ficar claro que a decisão é do
  usuário.

O Solis escolhe o modo conforme a complexidade. Não usar vários modelos à toa em tarefa simples.

## 6. Model Router — qual modelo pra cada coisa

Os agentes não ficam presos a um modelo. Uma camada própria, o Model Router, escolhe o modelo
considerando:

- complexidade;
- qualidade necessária;
- velocidade;
- custo;
- disponibilidade;
- privacidade;
- permissões de uso.

Políticas iniciais (exemplos, não amarras):

- Qwen local pra tarefas simples;
- modelos locais pra processamento privado;
- Claude pra tarefas complexas, quando autorizado;
- GPT pra tarefas específicas, quando vale a pena;
- Gemini onde ele tiver vantagem.

Cada provedor tem um adaptador independente. O sistema acompanha consumo, custos,
disponibilidade e limites.

> **Não presumir que a assinatura de um provedor autoriza uso automatizado ou ilimitado por outros
> sistemas.** Respeitar APIs, contratos e termos de uso. (O mesmo vale hoje pro Claude: login do
> claude.ai serve pro uso pessoal; um produto precisa de chave de API — `VISAO.md`.)

## 7. Solis Research & Development

Um departamento que investiga continuamente oportunidades pro Solis: evolução supervisionada.

**7.1 Pesquisa proativa.** Agentes pesquisam novidades em fontes como:

- YouTube;
- TikTok;
- Instagram;
- documentação técnica;
- repositórios;
- artigos;
- comunidades de tecnologia;
- ferramentas e frameworks novos.

Cada fonte depende dos meios de acesso, das APIs e das permissões dela.

**7.2 Identificação de oportunidades.** Os agentes procuram:

- tecnologias novas;
- ferramentas interessantes;
- arquiteturas novas;
- melhorias pro Solis;
- oportunidades de automação;
- funcionalidades que agreguem valor.

**7.3 Desenvolvimento supervisionado.** Achou uma oportunidade:

1. Pesquisar a solução.
2. Consultar modelos diferentes.
3. Comparar alternativas.
4. Avaliar a compatibilidade com o Solis.
5. Apresentar uma proposta.
6. Pedir aprovação.
7. Desenvolver um protótipo isolado, se autorizado.
8. Rodar testes.
9. Apresentar os resultados.
10. Pedir aprovação pra integrar no produto principal.

> **Os agentes nunca alteram sozinhos a versão principal do Solis.**

**7.4 Relatórios proativos.** O usuário pode receber relatórios com:

- as descobertas;
- as fontes;
- a relevância;
- as aplicações possíveis;
- comparações;
- recomendações;
- os protótipos disponíveis.

No futuro, avaliar avisos por WhatsApp, só por integrações oficiais e autorizadas (a API oficial
da Meta, como já decidido).

## 8. Ferramentas de desenvolvimento

O Solis precisa de capacidades de desenvolvimento comparáveis às do Claude Code. Não basta
conversar sobre código: ele tem de fazer trabalho real.

- ler arquivos;
- criar arquivos;
- editar projetos;
- rodar comandos de terminal;
- trabalhar com git;
- rodar testes;
- inspecionar erros;
- consultar documentação;
- pesquisar na web;
- analisar a estrutura de projetos;
- coordenar agentes desenvolvedores.

Avaliar integração com ferramentas e CLIs externas quando permitido, sempre com controles de
segurança, permissões e isolamento. O objetivo é uma plataforma de desenvolvimento completa, não
só uma interface de chat.

## 9. Autonomia e supervisão

**Princípio central:** os agentes têm iniciativa, mas não autoridade ilimitada.

**Pode ser automático, dentro das permissões:**

- pesquisa;
- análise;
- planejamento;
- organização;
- comparações;
- desenvolvimento em ambiente isolado;
- testes;
- relatórios.

**Exige autorização:**

- mudanças importantes na versão principal;
- instalar ferramentas;
- mudar configuração sensível;
- apagar dados;
- acessar informação protegida;
- mandar informação pra serviços externos;
- publicar, ou qualquer ação com impacto externo.

Tudo com registro de atividades e decisões.

## 10. Arquitetura técnica discutida (proposta, não decisão)

> É uma proposta da conversa, **não autorização pra trocar tecnologias que o Solis já usa.**
> Antes de adotar qualquer peça, verificar a arquitetura atual, as dependências, a compatibilidade
> e o benefício real.

| Camada | Proposta |
|---|---|
| Frontend | React, TypeScript, Tailwind, Tauri 2 (o que o Solis já usa) |
| Escritório virtual | PixiJS 8, 2D, personagens e animações isométricas |
| Backend | Python, FastAPI (o que o Solis já usa) |
| Orquestração | LangGraph como candidato; avaliar implementação própria quando fizer sentido |
| Banco | SQLite no começo (o que o Solis já usa) |
| Comunicação | WebSocket, eventos internos |
| Modelos | Ollama, Anthropic, OpenAI, Gemini, adaptadores futuros |
| Infraestrutura | local + nuvem, execução independente da tela, filas de tarefas, execuções persistidas, sistema de permissões |

## 11. Modelo de dados (conceito)

Três conceitos separados:

- **Agente:** a identidade permanente.
- **Tarefa:** o objetivo a cumprir.
- **Execução:** uma vez em que um agente trabalhou.

Uma tarefa pode envolver vários agentes, e um mesmo agente tem muitas execuções ao longo do tempo.

Entidades consideradas: agents, agent_skills, agent_tools, tasks, task_dependencies, executions,
agent_events, approvals, model_providers, model_usage, memories. A implementação se adapta ao banco
e aos padrões que o Solis já tem (as migrações de `banco.py`).

## 12. Primeiro MVP — Solis Agent Office 0.1

Validar a arquitetura com cinco agentes. **Missão de demonstração:** "Pesquise as melhores
arquiteturas pra implementar memória persistente num assistente pessoal de IA. Compare as opções e
entregue uma recomendação técnica."

**Fluxo:**

1. O usuário manda a missão.
2. O Solis Manager interpreta.
3. O Manager divide o trabalho.
4. Atlas pesquisa as alternativas.
5. Athena organiza a documentação.
6. Nexus propõe uma arquitetura.
7. Sentinel revisa os resultados.
8. O Manager consolida a entrega.
9. O Solis apresenta o relatório.

**O MVP tem de mostrar:**

- os cinco agentes cadastrados;
- execução com vários agentes;
- o Model Router;
- modelos locais e externos;
- execução em paralelo;
- comunicação estruturada;
- aprovação humana;
- histórico de atividades;
- persistência;
- o escritório isométrico;
- estados visuais sincronizados;
- recuperação de tarefas pendentes.

**Fica de fora no começo:**

- agentes criando outros agentes sozinhos;
- escritório multiplayer;
- operação irrestrita 24/7;
- autonomia ilimitada;
- mudança automática na versão principal.

## 13. Aplicação corporativa — possibilidade futura

Na conversa apareceu um exemplo do trabalho do Matheus: extração de dados de estudos de
ecotoxicologia aguda (Daphnia magna e peixes). Especializações possíveis:

- leitura de documentos;
- extração de dados;
- análise de tabelas;
- comparação de estudos históricos;
- identificação de mudanças de campos;
- validação;
- rastreabilidade das informações;
- relatórios comparativos.

Exemplo: comparar estudos de anos diferentes pra achar campos novos, campos ausentes, mudanças de
método e de nomenclatura.

> É uma referência de aplicação da arquitetura, **não autorização pra colocar documentos ou
> informações da empresa no Solis pessoal.** Qualquer uso corporativo exige autorização expressa,
> ambiente aprovado e controles de privacidade, segurança, confidencialidade e governança de dados.
> **O Solis pessoal e um eventual ambiente corporativo ficam separados.**

## 14. Ordem de evolução (a discutida)

1. Consolidar a memória e a identidade atual do Solis.
2. Auditar e estabilizar a arquitetura que existe.
3. Planejar a integração do Agent Runtime.
4. Implementar os primeiros agentes.
5. Desenvolver o Model Router.
6. Implementar o Solis Council.
7. Construir o Agent Office.
8. Desenvolver o Research & Development.
9. Ampliar a autonomia supervisionada.
10. Avaliar a personalização e o fine-tuning de modelos locais.

Não interromper o trabalho atual do Claude Code sem necessidade.

## 15. Instruções pro Claude Code (do documento)

Antes de qualquer implementação desta visão:

1. Auditar o repositório atual.
2. Identificar o que já existe.
3. Identificar tecnologias e dependências.
4. Ver quais requisitos já estão implementados.
5. Identificar incompatibilidades de arquitetura.
6. Registrar oportunidades de integração.
7. Identificar riscos e dependências.
8. Separar o que está definido do que ainda é proposta não aprovada.

**E também:**

- Documentar esta visão no projeto, seguindo as convenções que já existem. (Este arquivo faz isso.)
- Não reescrever módulos que funcionam sem necessidade.
- Não implementar tudo de uma vez.
- Não trazer dependências só porque foram citadas como possibilidade.
- Não inventar requisitos.
- Toda decisão de arquitetura importante que não esteja definida vai pro Matheus.
- Desenvolvimento progressivo, validado a cada etapa.

**Regra principal:** o Solis evolui a partir das decisões do Matheus. Os agentes podem propor,
questionar e fazer protótipos, mas a direção do produto é dele.

---

## Onde o Solis já está (13/11/2026)

Um primeiro levantamento, pra quando esta frente começar. Não é a auditoria completa do item 15:
essa se faz na hora.

- **Memória persistente (2.1):** existe.
  - Memórias, conversas, resumo, busca por significado e a extração do que aprender
    (`backend/solis/memoria.py`, `busca.py`).
  - **Defeito conhecido:** a extração às vezes transforma pedido em tarefa (`ESCOPO.md`).
- **Vários modelos (5, 6):** existe um roteador simples.
  - A conversa já escolhe entre o local, o Claude, o Codex, o Groq e o Gemini, com a privacidade
    decidindo o que pode sair da máquina (`roteador.py`, `cerebros.py`).
  - Não é ainda o Model Router desta visão: não pesa custo, qualidade nem tarefa.
- **Ferramentas de desenvolvimento (8):** quase todas existem, pelo Claude Agent SDK
  (`PARIDADE.md` → "Trabalhar num projeto"):
  - ler, escrever, editar, terminal ao vivo, comandos em segundo plano;
  - git na tela, voltar atrás, modos de aprovação;
  - ajudantes (subagentes) visíveis.
- **Aprovação humana e registro (5.5, 9):** existe.
  - O cartão de aprovação antes de escrever, editar ou rodar comando.
  - O registro de ações (`banco.acoes`).
- **Agentes como identidades (3), Council (5), Agent Office (4), R&D (7):** ainda não existem. Os
  ajudantes de hoje são os subagentes do Claude Code, sem identidade própria nem escritório.
