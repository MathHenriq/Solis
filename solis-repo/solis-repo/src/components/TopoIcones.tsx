import { Icone } from './icons';
import { SolisSimbolo } from './SolisSimbolo';

/** Cabeçalho do modo "barra de ícones".
 *
 *  Sem sidebar, a marca some da tela — e com ela some a única âncora que diz
 *  onde a pessoa está. Este cabeçalho devolve a marca ao topo, na horizontal, e
 *  leva os dois atalhos que na sidebar viviam no bloco de perfil.
 *  Referência: referencias/telas/12-conversa-barra-icones.png.
 *
 *  `fixed` e não no fluxo: a Conversa centraliza o conteúdo na altura da janela
 *  neste modo, e um cabeçalho no fluxo empurraria esse centro pra baixo. */
export function TopoIcones() {
  return (
    <header
      aria-label="Marca e atalhos"
      className="fixed inset-x-0 top-0 flex items-center pointer-events-none"
      style={{ height: 'var(--topo-h)', zIndex: 3 }}
    >
      {/* Quem centraliza é o NOME, não o lockup inteiro — o símbolo fica absoluto
          à esquerda dele e sai da conta.

          A referência centraliza a caixa do lockup (medido: caixa a -1,5px do
          centro, nome a +58,5px). O app fazia igual, e ficava menos deslocado que
          ela (+32px numa janela de 1919). Mas o olho não lê a caixa: ele traça a
          linha do meio de "SOLIS" e cobra que a cápsula e os atalhos caiam nela.
          Divergência da referência ASSUMIDA, e é a única do projeto — registrada
          em layout.iconBar._alinhamentoDoNome.

          O paddingLeft compensa o letter-spacing, que o CSS aplica também depois
          da última letra: sem ele a caixa é assimétrica e centralizá-la não
          centralizaria a palavra. */}
      <div className="relative mx-auto">
        <SolisSimbolo
          className="absolute right-full top-1/2 -translate-y-1/2 mr-lg text-text-primary"
          style={{ width: 48, height: 'auto' }}
        />
        <span
          className="font-wordmark text-text-primary"
          style={{ fontSize: 20, letterSpacing: 'var(--wordmark-tracking)', paddingLeft: 'var(--wordmark-tracking)' }}
        >
          SOLIS
        </span>
      </div>
      <div className="absolute right-2xl flex items-center gap-xl text-text-secondary pointer-events-auto">
        <button type="button" aria-label="Notificações"><Icone nome="sino" tamanho={22} /></button>
        <button type="button" aria-label="Perfil"><Icone nome="perfil" tamanho={22} /></button>
      </div>
    </header>
  );
}
