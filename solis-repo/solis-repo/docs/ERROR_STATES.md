# Solis — Estados de Erro, Vazio e Permissão

Regra geral de tom (herdada do princípio "calma" da seção 20 do DS): o Solis nunca se desculpa, nunca é vago sobre o que aconteceu, e sempre diz o que fazer a seguir. Frase curta, verbo ativo, sem ponto de exclamação.

## 1. Permissão de microfone negada

Isso desliga a Camada 3 da assinatura (glow reativo ao áudio) inteira pra esse usuário — precisa de tratamento explícito, não pode falhar silenciosamente.

- **Onde acontece:** primeira vez que o usuário tenta usar voz (tela Conversa ou onboarding).
- **Comportamento visual:** símbolo permanece no estado `idle` normal (camadas 1 e 2 continuam funcionando — só a 3 é que não ativa). Nunca mostrar o símbolo "quebrado" ou um ícone de erro genérico sobre ele; isso violaria "Solis parece presente mesmo parado".
- **Texto:**
  - Título: "Microfone desativado"
  - Corpo: "Sem acesso ao microfone, o Solis só responde por texto. Ativar em Configurações do sistema."
  - Ação: botão que abre as configurações de privacidade do SO (ou, se tecnicamente não for possível abrir direto, instrução de onde encontrar).
- **Fallback funcional:** o campo de texto do chat continua 100% disponível — a ausência de voz não pode travar a conversa.

## 2. Ollama indisponível (LLM local não responde)

- **Onde acontece:** qualquer chamada ao LLM local que der timeout ou erro de conexão.
- **Comportamento visual:** símbolo entra em `idle`, nunca fica travado em `thinking` indefinidamente — definir um timeout (sugestão: 8–10s) depois do qual o estado volta pra `idle` e o erro aparece.
- **Texto:**
  - Na mensagem do chat, no lugar da resposta: "Não consegui acessar o modelo local. Verificar se o Ollama está rodando."
  - Não usar linguagem técnica de stack trace na interface — isso é para o painel de configurações/logs, não para o balão de chat.

## 3. Memória vazia (usuário novo, nenhum item ainda)

- **Onde acontece:** tela Memória, antes de qualquer conversa gerar itens.
- **Texto:** "Nada guardado ainda. Conforme vocês conversam, o Solis vai lembrando do que for relevante aqui."
- Não usar ilustração genérica de "caixa vazia" — o próprio símbolo do Solis em `idle`, centralizado, já comunica isso sem precisar de arte adicional (reaproveita asset, mais leve).

## 4. Conversa vazia (chat aberto pela primeira vez)

- Já coberto no protótipo: mensagem inicial do próprio Solis ("Bom dia, Matheus. Como posso te ajudar hoje?"). Não é tecnicamente um "erro", mas é o mesmo padrão — nunca uma tela em branco sem direção.

## 5. Falha de STT/TTS (Whisper ou Piper não processam)

- **Comportamento visual:** se a transcrição falhar no meio da fala, o glow reativo (Camada 3) para suavemente (fade de opacity, não corte abrupto) e o estado volta a `idle`.
- **Texto:** "Não entendi o áudio. Tentar de novo ou digitar."
- Nunca travar o estado `listening` esperando um áudio que já falhou — isso quebraria a percepção de "presença" descrita na seção 20 (o Solis pareceria travado, não calmo).

## 6. Regra geral pra qualquer estado não listado aqui

Se surgir um erro/vazio não previsto neste documento durante a implementação: a pergunta de referência é "o que o Solis faria, calmamente, com essa informação?" — nunca um alerta genérico de sistema (ex: `alert()` do navegador, modal vermelho piscando). O erro é sempre uma mensagem dentro do fluxo normal da interface, no mesmo tom de voz do resto do produto.
