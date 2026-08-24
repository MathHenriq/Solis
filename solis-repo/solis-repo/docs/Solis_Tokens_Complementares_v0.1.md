# SOLIS — Tokens Complementares v0.1
Addendum ao Design System v0.1. Preenche lacunas deixadas em aberto no documento original (radius sem valor, cores semânticas sem hex, ausência de escala de elevação, e desalinhamento entre grid de ícones e escala do símbolo).

---

## 1. Contraste (WCAG 2.1)

Fórmula: contraste = (L1 + 0,05) / (L2 + 0,05), onde L é a luminância relativa de cada cor. AA exige ≥4,5:1 para texto normal, ≥3:1 para texto grande. AAA exige ≥7:1.

| Par | Contraste | Nível |
|---|---|---|
| Warm White `#F5F0E7` sobre Night `#071019` | 16,86:1 | AAA |
| Muted `#A1A7B3` sobre Deep `#0D1722` | 7,48:1 | AAA |
| Muted `#A1A7B3` sobre Night `#071019` | 7,92:1 | AAA |
| Night `#071019` (texto) sobre Solar `#FFB74D` (botão primary) | 11,06:1 | AAA |
| Success `#8FBF6D` sobre Night `#071019` | 8,97:1 | AAA |
| Error `#E4674A` sobre Night `#071019` | 5,78:1 | AA |
| Branco `#FFFFFF` sobre `color.bubble.user` `#AA6521` | 4,57:1 | AA |

> **Correção (verificada).** A primeira linha dizia 19,0:1. O valor real é
> **16,86:1**, conferido por três caminhos independentes (coloraide, o pacote
> npm wcag-contrast e cálculo em precisão decimal). Continua AAA com folga, ou
> seja, nenhuma decisão muda — mas o número estava errado. Os demais pares da
> tabela original foram conferidos e batem.
>
> Todos estes pares agora são verificados automaticamente por `npm run
> contraste`, que falha se algum deixar de cumprir o nível dele.

**Conclusão:** a paleta atual já é acessível nos pares principais. Não é preciso ajustar Solar, Muted ou Warm White. Isso precisa ser reverificado sempre que uma nova combinação de cor+fundo for proposta — não assumir, medir.

---

## 2. Radius — valores em px

O documento original cita tokens (`radius.sm/md/lg`) mas nenhum valor. Proposta alinhada à escala de espaçamento (múltiplos de 4):

| Token | Valor | Uso |
|---|---|---|
| `radius.sm` | 8px | Inputs, chips, botões pequenos |
| `radius.md` | 12px | Cards, botões padrão |
| `radius.lg` | 16px | Modais, painéis grandes |
| `radius.pill` | 999px | Botões pill / tags de estado |

Justificativa: seção 17.1 do DS já menciona "8–12px" para cards soltos no texto — aqui isso vira token nomeado e reutilizável, e ganha um valor para modais que antes não existia.

---

## 3. Elevação / Sombra

**Problema não tratado no v0.1:** `box-shadow` escuro tem efeito quase nulo sobre fundo já muito escuro (Night `#071019`, Deep `#0D1722`). Sombra não é a ferramenta certa de hierarquia neste sistema.

**Recomendação:** substituir "sombra" por **elevação via superfície + borda**, reservando glow (já definido na seção 7 do DS) para estados de atividade — não para hierarquia estática.

| Token | Composição | Uso |
|---|---|---|
| `elevation.0` | fundo Night, sem borda | Fundo base |
| `elevation.1` | fundo Deep, borda 1px `rgba(255,183,77,0.08)` | Cards em repouso |
| `elevation.2` | fundo Deep, borda 1px `rgba(255,183,77,0.16)` | Cards em hover/foco |
| `elevation.glow` | `elevation.2` + glow funcional (seção 7 do DS) | Elemento ativo/respondendo |

Isso mantém a filosofia "glow é funcional, não decorativo" (seção 7) e evita reintroduzir sombra tradicional, que a seção 21 já rejeita implicitamente ao banir "glassmorphism pesado".

---

## 4. Cores semânticas (Success / Error)

O DS cita "verde discreto" e "vermelho/âmbar controlado" sem hex — isso obriga quem implementa a decidir sozinho, gerando inconsistência entre telas. Proposta testada em contraste sobre Night:

| Token | Hex | Contraste s/ Night | Nível |
|---|---|---|---|
| `color.success` | `#8FBF6D` | 9,0:1 | AAA |
| `color.error` | `#E4674A` | 5,8:1 | AA |

Ambas dessaturadas o suficiente para não competir com Solar/Amber como acento principal — respeitam a regra "evitar cores extremamente saturadas" (seção 21).

---

## 5. Escala unificada Ícone ↔ Símbolo

O DS trata dois sistemas de escala sem conectá-los:
- Ícones: grid 24×24, testado apenas nesse tamanho.
- Símbolo: testado em 128/64/48/32/24/16px.

Eles se cruzam em 24px e 16px mas isso nunca é declarado. Proposta de escala única de tamanho (`size.icon`), evitando dois vocabulários para a mesma unidade:

| Token | Valor | Aplicação |
|---|---|---|
| `size.icon.xs` | 16px | Ícone inline, texto pequeno |
| `size.icon.sm` | 20px | Ícone padrão em componente |
| `size.icon.md` | 24px | Ícone de navegação (grid base) |
| `size.symbol.sm` | 32px | Símbolo em avatar pequeno |
| `size.symbol.md` | 48px | Símbolo em header |
| `size.symbol.lg` | 64px | Símbolo em splash/loading |
| `size.symbol.xl` | 128px | Símbolo em abertura/branding |

Com isso, ícone e símbolo compartilham a mesma escala base ao invés de dois testes de tamanho desconectados.

---

## 6. Pendências que ainda exigem decisão humana (não técnica)

- Fonte definitiva ainda não escolhida (seção 8 do DS lista 4 candidatas — nenhuma testada na interface real).
- Motion easing citado como "ease-in-out" mas sem duração em ms — sem isso, dev vai chutar valores diferentes em cada tela.
- Sequência de loading (seção 14: "núcleo → expansão → fechamento → repetição") não tem timing nem exemplo visual.

Essas três dependem de teste em produto real, não de cálculo — por isso ficaram fora dos tokens acima.
