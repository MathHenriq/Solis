import { useEffect, useState } from 'react';
import { Botao, Interruptor } from '../components/Controles';
import { Icone } from '../components/icons';
import { LinhaLista } from '../components/Tela';
import { estadoPc, guardarPastasPc, ligarPc, registroPc, type AcaoPc, type EstadoPc } from '../servidor';

/** A linha Arquivos da tela Ferramentas, de verdade (backend/solis/pc.py):
 *  ligada ou não, as pastas que o Solis pode ler, autorizar e tirar uma pasta;
 *  e embaixo da lista, o registro do que ele fez no computador.
 *
 *  PROVISÓRIO: desenho próprio sobre a linha da referência 14 (aprovada) — as
 *  pastas e o registro usam as ações em texto e o campo dos cartões já
 *  aprovados (Cérebros, Palavra de ativação). No navegador, a pasta é colada
 *  como caminho; no app Tauri, vira o seletor de pastas do Windows. */

const ROTULO: Record<string, string> = {
  listar_pasta: 'Olhou a pasta',
  buscar_arquivos: 'Procurou',
  ler_arquivo: 'Leu',
};
/** O que não deu certo não foi feito: "Tentou ler", e não "Leu". */
const TENTOU: Record<string, string> = {
  listar_pasta: 'Tentou olhar a pasta',
  buscar_arquivos: 'Tentou procurar',
  ler_arquivo: 'Tentou ler',
};

function hora(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function descrever(a: AcaoPc) {
  const alvo = String(a.argumentos.caminho ?? a.argumentos.nome ?? '');
  const base = (a.ok ? ROTULO : TENTOU)[a.ferramenta] ?? a.ferramenta;
  if (a.ferramenta === 'buscar_arquivos') return `${base} "${alvo}"`;
  if (a.ferramenta === 'listar_pasta' && !alvo) return 'Olhou as pastas autorizadas';
  return `${base} ${alvo}`;
}

export function useArquivos() {
  const [estado, definirEstado] = useState<EstadoPc | null | undefined>(undefined);
  const [registro, definirRegistro] = useState<AcaoPc[]>([]);
  useEffect(() => {
    estadoPc().then((r) => definirEstado(r.ok ? r.dados : null));
    registroPc().then((r) => r.ok && definirRegistro(r.dados));
  }, []);
  return { estado, definirEstado, registro };
}

export function LinhaArquivos({
  estado,
  aoMudar,
}: {
  estado: EstadoPc | null | undefined;
  aoMudar: (e: EstadoPc) => void;
}) {
  const [colando, definirColando] = useState(false);
  const [caminho, definirCaminho] = useState('');
  const [erro, definirErro] = useState<string | null>(null);

  async function guardar(pastas: string[]) {
    const r = await guardarPastasPc(pastas);
    if (r.ok) {
      aoMudar(r.dados);
      definirErro(null);
      return true;
    }
    definirErro(r.motivo ? `Não é uma pasta: ${caminho.trim()}` : 'Servidor do Solis desligado.');
    return false;
  }

  const descricao =
    estado === null
      ? 'Servidor do Solis desligado.'
      : !estado || estado.pastas.length
        ? 'Ler as pastas que você autorizar. Só lê: não cria, não muda e não apaga nada.'
        : 'Nenhuma pasta autorizada ainda. Autorize uma pra o Solis poder ler os seus arquivos.';

  return (
    <LinhaLista hover={false}>
      <div className="flex items-start gap-xl">
        <span className="text-text-secondary shrink-0" style={{ marginTop: 2 }}>
          <Icone nome="arquivos" tamanho={26} />
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-text-primary" style={{ fontSize: 'var(--cfg-secao)' }}>Arquivos</div>
          <div className="text-text-secondary" style={{ fontSize: 'var(--mem-origem)', marginTop: 'var(--mem-origem-top)' }}>
            {descricao}
          </div>
          {estado && estado.pastas.length > 0 && (
            <ul style={{ marginTop: 'var(--mac-botao-top)' }}>
              {estado.pastas.map((p) => (
                <li key={p} className="flex items-center group" style={{ gap: 'var(--cer-controles-gap)', fontSize: 'var(--mem-origem)' }}>
                  <span className="text-text-primary truncate" title={p}>{p}</span>
                  <button
                    type="button"
                    className="text-text-secondary hover:text-text-primary hover:underline shrink-0"
                    onClick={() => guardar(estado.pastas.filter((x) => x !== p))}
                  >
                    Tirar
                  </button>
                </li>
              ))}
            </ul>
          )}
          {estado && !colando && (
            <button
              type="button"
              className="text-accent hover:underline"
              style={{ fontSize: 'var(--mem-origem)', marginTop: 'var(--mac-botao-top)' }}
              onClick={() => definirColando(true)}
            >
              Autorizar pasta
            </button>
          )}
          {colando && estado && (
            <div style={{ marginTop: 'var(--mac-botao-top)', maxWidth: 'var(--cer-texto-max)' }}>
              <input
                autoFocus
                value={caminho}
                spellCheck={false}
                onChange={(e) => definirCaminho(e.target.value)}
                onKeyDown={async (e) => {
                  if (e.key === 'Enter' && caminho.trim() && (await guardar([...estado.pastas, caminho.trim()]))) {
                    definirColando(false);
                    definirCaminho('');
                  } else if (e.key === 'Escape') definirColando(false);
                }}
                placeholder="Cole o caminho da pasta, como C:\Users\Matheus\Documents"
                aria-label="Caminho da pasta"
                className="block w-full bg-transparent outline-none text-text-primary placeholder:text-text-secondary border border-divider focus:border-[color-mix(in_srgb,var(--accent)_55%,transparent)]"
                style={{ fontSize: 'var(--cfg-dica)', borderRadius: 'var(--mac-campo-raio)', padding: 'var(--mac-campo-py) var(--mac-campo-px)' }}
              />
              <div className="flex items-center" style={{ gap: 'var(--mac-botao-gap)', marginTop: 'var(--mac-botao-top)' }}>
                <Botao
                  tipo="destaque"
                  disabled={!caminho.trim()}
                  onClick={async () => {
                    if (await guardar([...estado.pastas, caminho.trim()])) {
                      definirColando(false);
                      definirCaminho('');
                    }
                  }}
                >
                  Autorizar
                </Botao>
                <Botao onClick={() => definirColando(false)}>Cancelar</Botao>
              </div>
            </div>
          )}
          {erro && (
            <p className="text-[var(--erro)]" style={{ fontSize: 'var(--mem-origem)', marginTop: 'var(--mac-botao-top)' }}>
              {erro}
            </p>
          )}
        </div>
        <Interruptor
          ligado={!!estado?.ligada}
          rotulo="Arquivos"
          aoTrocar={
            estado
              ? async (v) => {
                  const r = await ligarPc(v);
                  if (r.ok) aoMudar(r.dados);
                }
              : undefined
          }
        />
      </div>
    </LinhaLista>
  );
}

/** O que o Solis fez no computador, do mais novo pro mais antigo. */
export function Registro({ acoes }: { acoes: AcaoPc[] }) {
  if (!acoes.length) return null;
  return (
    <section style={{ marginTop: 'var(--cfg-linha-pad)' }}>
      <h2 className="text-text-primary" style={{ fontSize: 'var(--cfg-secao)' }}>O que o Solis fez</h2>
      <ul style={{ marginTop: 'var(--mem-origem-top)' }}>
        {acoes.map((a) => (
          <li
            key={a.id}
            className="flex border-b border-divider"
            style={{
              gap: 'var(--cer-controles-gap)',
              fontSize: 'var(--mem-origem)',
              paddingTop: 'var(--mac-botao-top)',
              paddingBottom: 'var(--mac-botao-top)',
            }}
          >
            <span className="text-text-secondary shrink-0 tabular-nums">{hora(a.quando)}</span>
            <span className={`min-w-0 truncate ${a.ok ? 'text-text-primary' : 'text-[var(--erro)]'}`} title={a.resultado}>
              {descrever(a)}
              {!a.ok && ` — ${a.resultado}`}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
