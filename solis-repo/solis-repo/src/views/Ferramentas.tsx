import { Icone, type NomeIcone } from '../components/icons';
import { LinhaColuna, TelaColuna } from '../components/TelaNova';
import { LinhaArquivos, Registro, useArquivos } from './FerramentaArquivos';

/** Ferramentas — o que o Solis pode e não pode fazer.
 *  Referência: referencias/telas/14-ferramentas.png.
 *
 *  Esta tela é de CONFIANÇA antes de ser de configuração: é onde a pessoa vê,
 *  numa olhada, o alcance que deu ao assistente. Por isso os interruptores ficam
 *  todos numa coluna alinhada — inclusive o da linha com permissão negada, que
 *  numa das gerações da referência saía da coluna. Ver
 *  referencias/telas/_variantes/LEIA-ME.md.
 *
 *  PROVISÓRIO: o estado é local. A permissão de verdade vem do sistema
 *  operacional, via Tauri, e "Abrir configurações do sistema" vai abrir o painel
 *  nativo.
 *
 *  PROVISÓRIO — visual novo (27/11/2026, layout.visualNovo.tela): a moldura da
 *  Memória e de Modelos locais, as linhas sem o véu do hover (são linhas de
 *  ajuste, não um alvo inteiro) e o interruptor de 64 x 32, na escala da
 *  referência 14. */

type Ferramenta = {
  id: string;
  nome: string;
  descricao: string;
  icone: NomeIcone;
  ligada: boolean;
  negada?: boolean;
  aviso?: string;
};

const FERRAMENTAS: Ferramenta[] = [
  { id: 'voz', nome: 'Voz', descricao: 'Ouvir o que você fala e transcrever', icone: 'microfone', ligada: true },
  { id: 'fala', nome: 'Fala', descricao: 'Responder em voz alta', icone: 'fala', ligada: true },
  { id: 'visao', nome: 'Visão', descricao: 'Enxergar o que está na sua tela quando você pedir', icone: 'visao', ligada: false, negada: true },
  { id: 'web', nome: 'Web', descricao: 'Pesquisar na internet quando não souber', icone: 'web', ligada: true },
  {
    id: 'terminal', nome: 'Terminal', descricao: 'Rodar comandos na sua máquina', icone: 'terminal', ligada: false,
    aviso: 'Desligada por padrão. Só ligue se souber o que está fazendo.',
  },
  { id: 'agenda', nome: 'Agenda', descricao: 'Ver e criar compromissos', icone: 'agenda', ligada: true },
];

function Interruptor({ ligado, desabilitado, rotulo }: { ligado: boolean; desabilitado?: boolean; rotulo: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={ligado}
      aria-label={rotulo}
      disabled={desabilitado}
      className={`shrink-0 flex items-center ${ligado ? 'bg-accent' : 'bg-divider'} ${desabilitado ? 'opacity-60' : ''}`}
      style={{
        width: 'var(--cfg-sw-l)', height: 'var(--cfg-sw-h)', borderRadius: 999, padding: 4,
        justifyContent: ligado ? 'flex-end' : 'flex-start',
      }}
    >
      {/* Desligado, a bolinha não pode ser da cor do fundo: no dark ela some no
          trilho escuro (a mesma regra do Interruptor de Controles). */}
      <span
        className={`block ${ligado ? 'bg-canvas' : 'bg-text-secondary'}`}
        style={{ width: 'calc(var(--cfg-sw-h) - 8px)', height: 'calc(var(--cfg-sw-h) - 8px)', borderRadius: 999 }}
      />
    </button>
  );
}

/** O aviso da permissão que o sistema negou, com o caminho pra liberar. */
function PermissaoNegada() {
  return (
    <>
      <div style={{ color: 'var(--erro)' }}>Permissão negada</div>
      {/* O alinhamento vem de quem envolve: à direita ao lado da linha, à
          esquerda embaixo da descrição (o botão centralizaria a quebra). */}
      <button type="button" className="text-text-secondary underline" style={{ marginTop: 4, textAlign: 'inherit' }}>
        Abrir configurações do sistema
      </button>
    </>
  );
}

/** Onde a linha Arquivos entra: depois da Web, como na referência 14. */
const ANTES_DE_ARQUIVOS = FERRAMENTAS.findIndex((f) => f.id === 'terminal');

export function Ferramentas() {
  // Arquivos é a primeira de verdade (pc.py); as outras ainda são de exemplo.
  const arquivos = useArquivos();
  const ativas = FERRAMENTAS.filter((f) => f.ligada).length + (arquivos.estado?.ligada ? 1 : 0);
  return (
    <TelaColuna titulo="Ferramentas" subtitulo={`${ativas} de ${FERRAMENTAS.length + 1} ativas`}>
      {FERRAMENTAS.slice(0, ANTES_DE_ARQUIVOS).map(linha)}
      <LinhaArquivos estado={arquivos.estado} aoMudar={arquivos.definirEstado} />
      {FERRAMENTAS.slice(ANTES_DE_ARQUIVOS).map(linha)}
      <Registro acoes={arquivos.registro} />
    </TelaColuna>
  );
}

function linha(f: Ferramenta) {
  return (
    <LinhaColuna key={f.id} fixa>
      {/* O ícone, o aviso e o interruptor se centram no nome com a descrição
          (--vn-ajuste-h), e não no bloco inteiro: no Terminal, que tem o aviso
          embaixo, eles ficam na altura do nome, como na referência. */}
      <div className="flex items-start gap-xl">
        <span className="text-text-secondary shrink-0 flex items-center" style={{ height: 'var(--vn-ajuste-h)' }}>
          <Icone nome={f.icone} tamanho={26} />
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-text-primary" style={{ fontSize: 'var(--cfg-secao)' }}>{f.nome}</div>
          <div className="text-text-secondary" style={{ fontSize: 'var(--mem-origem)', marginTop: 'var(--mem-origem-top)' }}>
            {f.descricao}
          </div>
          {f.aviso && (
            <div className="text-text-secondary" style={{ fontSize: 'var(--mem-origem)', marginTop: 'var(--mem-origem-top)' }}>
              {f.aviso}
            </div>
          )}
          {/* No celular não cabe ao lado: o aviso desce pra baixo da descrição. */}
          {f.negada && (
            <div className="md:hidden" style={{ fontSize: 'var(--mem-origem)', marginTop: 'var(--mem-origem-top)' }}>
              <PermissaoNegada />
            </div>
          )}
        </div>
        {f.negada && (
          <div
            className="hidden md:flex text-right shrink-0 flex-col justify-center"
            style={{ fontSize: 'var(--mem-data)', minHeight: 'var(--vn-ajuste-h)' }}
          >
            <PermissaoNegada />
          </div>
        )}
        <span className="shrink-0 flex items-center" style={{ height: 'var(--vn-ajuste-h)' }}>
          <Interruptor ligado={f.ligada} desabilitado={f.negada} rotulo={f.nome} />
        </span>
      </div>
    </LinhaColuna>
  );
}
