import { useCallback, useEffect, useRef, useState } from 'react';
import { Icone, type NomeIcone } from '../components/icons';
import { BotaoContorno, Tela } from '../components/Tela';
import {
  listarDocumentos,
  removerDocumento,
  uploadDocumento,
  type Documento,
} from '../lib/solisApi';

/** Conhecimento — os documentos que a pessoa deu pro Solis ler.
 *  Referência: referencias/telas/17-conhecimento.png.
 *
 *  Não confundir com Memória: lá são fatos curtos que ele aprendeu sozinho; aqui
 *  são fontes que ela entregou. Por isso grade de cartões e não lista — cada
 *  fonte é um objeto com identidade, não uma linha de texto.
 *
 *  A grade agora vem do backend (/knowledge/documents). O cartão é o mesmo da
 *  referência; o que mudou foi de onde vêm nome, tipo e detalhe, e que a barra
 *  de progresso passou a marcar o processamento de verdade em vez de um número
 *  fixo. */

const ACEITOS = '.pdf,.docx,.txt,.md';

/** Extensão → ícone e rótulo do tipo. O acervo é de arquivo, então 'web' e
 *  'arquivos' ficam de fora até existir ingestão de URL. */
const PORTIPO: Record<string, { icone: NomeIcone; rotulo: string }> = {
  pdf: { icone: 'documento', rotulo: 'PDF' },
  docx: { icone: 'documento', rotulo: 'DOCX' },
  txt: { icone: 'nota', rotulo: 'Texto' },
  md: { icone: 'nota', rotulo: 'Markdown' },
};

function tipoDe(nome: string) {
  const ext = nome.slice(nome.lastIndexOf('.') + 1).toLowerCase();
  return PORTIPO[ext] ?? { icone: 'documento' as NomeIcone, rotulo: ext.toUpperCase() || 'Arquivo' };
}

const plural = (n: number, um: string, muitos: string) => `${n} ${n === 1 ? um : muitos}`;

export function Conhecimento() {
  const [busca, definirBusca] = useState('');
  const [documentos, definirDocumentos] = useState<Documento[]>([]);
  const [carregando, definirCarregando] = useState(true);
  const [semBackend, definirSemBackend] = useState(false);
  // Nomes em processamento. É lista e não booleano porque dá pra escolher
  // vários arquivos de uma vez, e cada um vira um cartão enquanto não termina.
  const [processando, definirProcessando] = useState<string[]>([]);
  // Remoção em dois toques: o primeiro arma, o segundo apaga. Sem confirm() do
  // navegador — ERROR_STATES.md §6 descarta o diálogo genérico do sistema, e
  // apagar documento com um clique solto é fácil demais.
  const [confirmando, definirConfirmando] = useState<number | null>(null);

  const entrada = useRef<HTMLInputElement>(null);

  const recarregar = useCallback(async () => {
    try {
      definirDocumentos(await listarDocumentos());
      definirSemBackend(false);
    } catch {
      // A tela não quebra com o backend parado: mostra o que houve e segue.
      definirSemBackend(true);
    } finally {
      definirCarregando(false);
    }
  }, []);

  useEffect(() => {
    void recarregar();
  }, [recarregar]);

  const enviar = useCallback(
    async (arquivos: FileList | null) => {
      if (!arquivos?.length) return;
      const lista = Array.from(arquivos);
      definirProcessando((p) => [...p, ...lista.map((a) => a.name)]);

      // Um de cada vez: o backend extrai texto numa thread, e mandar cinco PDFs
      // juntos só enfileira lá dentro com mais memória ocupada aqui.
      for (const arquivo of lista) {
        try {
          const documento = await uploadDocumento(arquivo);
          // Arquivo ilegível volta com status 'erro' — é um documento na lista,
          // não uma exceção. Só a falha de rede cai no catch.
          definirDocumentos((d) => [documento, ...d]);
          definirSemBackend(false);
        } catch {
          definirSemBackend(true);
        } finally {
          definirProcessando((p) => {
            const i = p.indexOf(arquivo.name);
            return i === -1 ? p : [...p.slice(0, i), ...p.slice(i + 1)];
          });
        }
      }
    },
    [],
  );

  const remover = useCallback(async (id: number) => {
    try {
      await removerDocumento(id);
      definirDocumentos((d) => d.filter((x) => x.id !== id));
    } catch {
      definirSemBackend(true);
    } finally {
      definirConfirmando(null);
    }
  }, []);

  const filtro = busca.trim().toLowerCase();
  const vistos = filtro ? documentos.filter((d) => d.name.toLowerCase().includes(filtro)) : documentos;

  const prontos = documentos.filter((d) => d.status === 'processado');
  const trechos = prontos.reduce((soma, d) => soma + d.n_chunks, 0);
  const subtitulo = semBackend
    ? 'Backend do Solis fora do ar'
    : carregando
      ? 'Carregando…'
      : `${plural(prontos.length, 'fonte', 'fontes')} · ${plural(trechos, 'trecho indexado', 'trechos indexados')}`;

  return (
    <Tela
      titulo="Conhecimento"
      subtitulo={subtitulo}
      acao={
        <BotaoContorno onClick={() => entrada.current?.click()}>
          <span style={{ fontSize: 20, lineHeight: 1 }}>+</span> Adicionar fonte
        </BotaoContorno>
      }
    >
      {/* Fora da grade e invisível: o botão da referência é o BotaoContorno, e
          um <input type="file"> não se estiliza de forma confiável entre
          plataformas. Ele existe só pra abrir o seletor do sistema. */}
      <input
        ref={entrada}
        type="file"
        accept={ACEITOS}
        multiple
        className="hidden"
        onChange={(e) => {
          void enviar(e.target.files);
          // Zera o valor pra que escolher O MESMO arquivo de novo dispare
          // outro change — sem isso, subir de novo depois de um erro não faz nada.
          e.target.value = '';
        }}
      />

      <div
        className="flex items-center border border-divider"
        style={{ height: 'var(--mem-busca-h)', borderRadius: 'var(--mem-busca-raio)', marginBottom: 'var(--mem-lista-gap)' }}
      >
        <span className="text-text-secondary shrink-0" style={{ paddingLeft: 22, paddingRight: 16 }}>
          <Icone nome="buscar" tamanho={19} />
        </span>
        <input
          className="flex-1 bg-transparent outline-none text-text-primary placeholder:text-text-placeholder"
          style={{ fontSize: 'var(--mem-item-texto)', paddingRight: 22 }}
          placeholder="Buscar no conhecimento…"
          aria-label="Buscar no conhecimento"
          value={busca}
          onChange={(e) => definirBusca(e.target.value)}
        />
      </div>

      {semBackend && (
        <p className="text-text-secondary" style={{ fontSize: 'var(--mem-item-texto)' }}>
          Não consegui falar com o backend do Solis. Verificar se o serviço local está rodando.
        </p>
      )}

      {!semBackend && !carregando && documentos.length === 0 && processando.length === 0 && (
        <p className="text-text-secondary" style={{ fontSize: 'var(--mem-item-texto)' }}>
          Nenhuma fonte ainda. Adicionar um PDF, DOCX, TXT ou MD para o Solis poder consultar.
        </p>
      )}

      <div className="grid grid-cols-3" style={{ gap: 'var(--cfg-mini-gap)' }}>
        {processando.map((nome) => (
          <Cartao key={`processando-${nome}`} nome={nome} icone={tipoDe(nome).icone}>
            <div style={{ marginTop: 12 }}>
              {/* Barra de progresso desenhada, não <progress>: o nativo não
                  aceita altura nem cor consistentes entre navegadores.
                  Cheia e sem número: o backend extrai e indexa numa tacada só,
                  não há percentual real pra reportar, e inventar um seria
                  mostrar um progresso que não existe. */}
              <div className="bg-divider" style={{ height: 4, borderRadius: 999 }}>
                <div className="bg-accent" style={{ width: '100%', height: 4, borderRadius: 999 }} />
              </div>
              <div className="text-text-secondary" style={{ fontSize: 'var(--mem-origem)', marginTop: 10 }}>
                Processando…
              </div>
            </div>
          </Cartao>
        ))}

        {vistos.map((d) => (
          <Cartao
            key={d.id}
            nome={d.name}
            icone={tipoDe(d.name).icone}
            acao={
              <button
                type="button"
                className={confirmando === d.id ? 'text-accent' : 'text-text-secondary'}
                style={{ fontSize: 'var(--mem-origem)' }}
                aria-label={confirmando === d.id ? `Confirmar remoção de ${d.name}` : `Remover ${d.name}`}
                onClick={() => (confirmando === d.id ? void remover(d.id) : definirConfirmando(d.id))}
                onBlur={() => definirConfirmando((c) => (c === d.id ? null : c))}
              >
                {confirmando === d.id ? 'Remover?' : <Icone nome="mais" tamanho={18} />}
              </button>
            }
          >
            {d.status === 'erro' ? (
              // O erro fica na linha do documento, e não some: sem ele o
              // usuário sobe o mesmo PDF escaneado de novo sem saber por quê.
              <div className="text-text-secondary" style={{ fontSize: 'var(--mem-origem)', marginTop: 'var(--mem-origem-top)' }}>
                <span className="text-accent">Não indexado</span> — {d.error}
              </div>
            ) : (
              <div className="text-text-secondary" style={{ fontSize: 'var(--mem-origem)', marginTop: 'var(--mem-origem-top)' }}>
                {tipoDe(d.name).rotulo} · {plural(d.n_chunks, 'trecho', 'trechos')}
              </div>
            )}
          </Cartao>
        ))}
      </div>
    </Tela>
  );
}

/** O cartão da referência. Extraído porque a grade agora desenha dois tipos de
 *  linha — o documento indexado e o que ainda está processando — e os dois têm
 *  que sair com a mesma caixa, o mesmo raio e o mesmo respiro. */
function Cartao({
  nome,
  icone,
  acao,
  children,
}: {
  nome: string;
  icone: NomeIcone;
  acao?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <article
      className="border border-divider hover:bg-[var(--mem-hover)]"
      style={{ borderRadius: 'var(--cfg-card-raio)', padding: 24 }}
    >
      <div className="flex items-start justify-between">
        <span className="text-text-secondary"><Icone nome={icone} tamanho={28} /></span>
        {acao}
      </div>
      <div
        className="text-text-primary"
        style={{ fontSize: 'var(--cfg-secao)', marginTop: 30, overflowWrap: 'anywhere' }}
      >
        {nome}
      </div>
      {children}
    </article>
  );
}
