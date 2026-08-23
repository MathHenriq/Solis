# REGRAS INVIOLÁVEIS — Solis (ler antes de QUALQUER tarefa)

Estas regras vêm antes de qualquer instrução específica. Não há exceção técnica, criativa ou de conveniência que as sobreponha. Se cumprir uma tarefa exigir quebrar uma destas regras, a tarefa PARA e o conflito é reportado — nunca se resolve desviando da regra.

## Regra 1 — As imagens de referência são a fonte da verdade

Antes de criar, editar ou estilizar qualquer coisa, olhar as imagens de referência do Matheus (as 6 telas + os assets de marca em `/referencias/`). Nada é criado "de memória" ou "por aproximação". A pergunta antes de escrever qualquer CSS é: "isso bate exatamente com a imagem?"

## Regra 2 — Divergência da referência é rejeitada

Qualquer cor, espaçamento, tamanho, ícone, tipografia, posição ou detalhe diferente do que está nas imagens de referência será RECUSADO. Não "parecido". Não "inspirado em". Idêntico. Valores devem ser extraídos/medidos das imagens (amostra de pixel para cor, medição em px para espaçamento), nunca estimados no olho.

## Regra 3 — Qualidade não se negocia com atalho técnico

Onde a fidelidade exigir um recurso melhor (modelo de imagem melhor, asset em resolução maior, biblioteca específica), usa-se o recurso. Não se entrega uma versão pior "porque foi o que deu". Se a qualidade não puder ser atingida com o que está à mão, isso é dito claramente ANTES de entregar — nunca se disfarça uma limitação como resultado final.

## Consequência prática dessas regras no fluxo

- Todo prompt ao Claude Code começa com: "Consulte as imagens de referência em /referencias/ antes de começar. Siga a Regra 2 (divergência = rejeitada)."
- Se o Claude Code produzir algo que diverge da referência, o certo é apontar exatamente onde divergiu e corrigir contra a imagem — não aceitar como "está bom o suficiente".
- Limitação real (ex: recorte de ícone pequeno demais, transparência que não existe no asset) é reportada como limitação, com o caminho de solução — não é empurrada como entrega.
