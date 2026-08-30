# Preview na Vercel

O front do Solis é um SPA Vite estático — nada dele depende do Tauri em runtime
(`@tauri-apps/api` está nas dependências mas ainda não é importado por nenhum arquivo de
`src/`). Então ele sobe na Vercel sem adaptação.

## Ligando

1. Vercel → **Add New… → Project** → importar `MathHenriq/Solis`.
2. **Não mexer em nada** na tela de configuração. O `vercel.json` da raiz já diz onde o app
   mora, como instalar, como buildar e onde fica a saída. Deixar "Root Directory" na raiz.
3. Deploy.

O `vercel.json` existe porque o app está aninhado em `solis-repo/solis-repo/`, e sem ele a
Vercel procuraria um `package.json` na raiz do repositório e falharia.

## O que esperar

- **É uma interface de desktop.** Foi medida contra referências de 1440 × 930 e não tem
  layout responsivo — abrir no celular vai parecer quebrado, e está certo assim: o Solis é
  um app de janela, não um site.
- **Os dados são de exemplo.** A lista de Memória é um array no próprio componente, marcado
  como `PROVISÓRIO`. Não há backend, não há banco, não há modelo. É o front.
- **A troca de tela funciona** — clicar em Conversa ou Memória na sidebar troca de verdade.
  As outras seis ainda caem na Conversa.
- **A troca de tema não tem interface ainda.** O tema é lido do `localStorage` antes do
  primeiro paint. Para ver os outros dois no preview, abrir o console e rodar:

      localStorage.setItem('solis.appearance.theme', 'espacial'); location.reload()

  Os valores válidos são `espacial`, `claro` e `dark`. E para desligar a foto de fundo:

      localStorage.setItem('solis.appearance.scene', 'off'); location.reload()

  Isso vira o card Aparência em Configurações quando essa tela for construída.

## Backend

Fica para depois do preview no ar, por decisão do Matheus. Quando entrar (SQLite+FTS5,
Ollama, Whisper, Piper), nada disso roda na Vercel — é tudo local, dentro do Tauri. O
preview continua sendo só a casca visual.
