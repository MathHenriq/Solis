import { Icone, type NomeIcone } from '../components/icons';
import { LinhaLista, Tela } from '../components/Tela';

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
 *  nativo. */

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
  { id: 'arquivos', nome: 'Arquivos', descricao: 'Ler e escrever nas pastas que você autorizar', icone: 'arquivos', ligada: true },
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
      <span
        className="block bg-canvas"
        style={{ width: 'calc(var(--cfg-sw-h) - 8px)', height: 'calc(var(--cfg-sw-h) - 8px)', borderRadius: 999 }}
      />
    </button>
  );
}

export function Ferramentas() {
  const ativas = FERRAMENTAS.filter((f) => f.ligada).length;
  return (
    <Tela titulo="Ferramentas" subtitulo={`${ativas} de ${FERRAMENTAS.length} ativas`}>
      {FERRAMENTAS.map((f) => (
        <LinhaLista key={f.id}>
          <div className="flex items-center gap-xl">
            <span className="text-text-secondary shrink-0"><Icone nome={f.icone} tamanho={26} /></span>
            <div className="flex-1">
              <div className="text-text-primary" style={{ fontSize: 'var(--cfg-secao)' }}>{f.nome}</div>
              <div className="text-text-secondary" style={{ fontSize: 'var(--mem-origem)', marginTop: 'var(--mem-origem-top)' }}>
                {f.descricao}
              </div>
              {f.aviso && (
                <div className="text-text-secondary" style={{ fontSize: 'var(--mem-origem)', marginTop: 'var(--mem-origem-top)' }}>
                  {f.aviso}
                </div>
              )}
            </div>
            {f.negada && (
              <div className="text-right shrink-0" style={{ fontSize: 'var(--mem-data)' }}>
                <div style={{ color: 'var(--erro)' }}>Permissão negada</div>
                <button type="button" className="text-text-secondary underline" style={{ marginTop: 4 }}>
                  Abrir configurações do sistema
                </button>
              </div>
            )}
            <Interruptor ligado={f.ligada} desabilitado={f.negada} rotulo={f.nome} />
          </div>
        </LinhaLista>
      ))}
    </Tela>
  );
}
