import { useEffect, useState } from 'react';
import { Icone } from '../components/icons';
import { EstadoVazio } from '../components/Tela';
import { listarMemorias, type Memoria as MemoriaGuardada, type Resultado } from '../servidor';

/** Tela de Memória — lista e busca.
 *
 *  Medidas de docs/solis-tokens.json → layout.memoria, tiradas de
 *  referencias/telas/09-memoria.png.
 *
 *  TODO O x DESTA TELA É MEDIDO A PARTIR DA DIVISÓRIA DA SIDEBAR, não da borda
 *  da janela: a referência veio com sidebar de 267px e a do app tem 200px, que
 *  é o valor das 3 telas de tema já aprovadas. Medir da borda deslocaria a tela
 *  inteira em 67px.
 *
 *  Da referência foi adotado o LAYOUT. A paleta dela (canvas #0D1216, divisória
 *  #232629, sidebar com superfície própria) NÃO foi: canvas e divisória estavam
 *  fechados desde as 3 telas de tema, o gerador recebeu os hexes exatos no
 *  prompt e não os respeitou. Ver layout.memoria._divergencias. */

const MES = new Intl.DateTimeFormat('pt-BR', { day: 'numeric', month: 'short' });

/** "hoje", "ontem", "há 3 dias", e a data a partir de uma semana — como a
 *  referência escreve. Conta dias de calendário, não blocos de 24h: uma memória
 *  das 23h é "ontem" à 1h da manhã seguinte. */
function quando(iso: string): string {
  const d = new Date(iso);
  const hoje = new Date();
  const dias = Math.round(
    (new Date(hoje.getFullYear(), hoje.getMonth(), hoje.getDate()).getTime() -
      new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()) /
      86_400_000,
  );
  if (dias <= 0) return 'hoje';
  if (dias === 1) return 'ontem';
  if (dias < 7) return `há ${dias} dias`;
  return MES.format(d).replace('.', '');
}

export function Memoria() {
  const [busca, definirBusca] = useState('');
  const [resultado, definirResultado] = useState<Resultado<MemoriaGuardada[]> | null>(null);

  useEffect(() => {
    let vivo = true;
    listarMemorias().then((r) => vivo && definirResultado(r));
    return () => {
      vivo = false;
    };
  }, []);

  const todas = resultado?.estado === 'ok' ? resultado.dados : [];
  // PROVISÓRIO: busca por trecho, no front. O FTS5 do SQLite entra quando a
  // lista crescer a ponto de não caber inteira na tela de uma vez.
  const filtradas = busca
    ? todas.filter((m) => (m.texto + m.tema).toLowerCase().includes(busca.toLowerCase()))
    : todas;

  // Antes da resposta, nem contagem nem vazio: piscaria "Nenhuma memória"
  // por um instante numa lista que tem memórias.
  const subtitulo =
    resultado?.estado !== 'ok'
      ? ''
      : todas.length === 0
        ? 'Nenhuma memória ainda'
        : `${todas.length} ${todas.length === 1 ? 'memória' : 'memórias'}`;

  // bg-canvas, e não fundo transparente como a Conversa: esta lista sangra até a
  // base da janela, e sobre a foto do horizonte o texto perderia o contraste que
  // a ancoragem da cena devolveu. A referência mostra fundo liso. O Horizonte
  // continua montado no shell — a Camada 1 não remonta —, só não aparece por
  // baixo desta tela.
  return (
    <main className="relative flex-1 flex flex-col overflow-hidden bg-canvas" style={{ zIndex: 1 }}>
      <div
        className="shrink-0"
        style={{
          paddingLeft: 'var(--mem-pad-l)',
          paddingRight: 'var(--mem-pad-r)',
          paddingTop: 'var(--mem-titulo-top)',
        }}
      >
        {/* O título é a única serifada da tela, como a saudação da Conversa. */}
        <h1
          className="font-display text-text-primary leading-none"
          style={{ fontSize: 'var(--mem-titulo)' }}
        >
          Memória
        </h1>

        <p
          className="text-text-secondary"
          style={{
            fontSize: 'var(--mem-contagem)',
            marginTop: 'var(--mem-contagem-gap)',
          }}
        >
          {subtitulo}
        </p>

        <div
          className="flex items-center border border-divider"
          style={{
            marginTop: 'var(--mem-busca-gap)',
            height: 'var(--mem-busca-h)',
            borderRadius: 'var(--mem-busca-raio)',
          }}
        >
          <span className="text-text-secondary shrink-0" style={{ paddingLeft: 22, paddingRight: 16 }}>
            <Icone nome="buscar" tamanho={19} />
          </span>
          <input
            className="flex-1 bg-transparent outline-none text-text-primary placeholder:text-text-placeholder"
            style={{ fontSize: 'var(--mem-item-texto)', paddingRight: 22 }}
            placeholder="Buscar nas memórias…"
            aria-label="Buscar nas memórias"
            value={busca}
            onChange={(e) => definirBusca(e.target.value)}
          />
        </div>
      </div>

      {/* A lista rola sozinha e sangra até a base da janela: na referência o
          sétimo item aparece cortado pela borda, e é esse corte que diz que há
          mais coisa abaixo. Por isso a lista não tem padding inferior. */}
      <ul
        className="flex-1 overflow-y-auto"
        style={{
          marginTop: 'var(--mem-lista-gap)',
          paddingLeft: 'var(--mem-pad-l)',
          paddingRight: 'var(--mem-pad-r)',
        }}
      >
        {filtradas.map((m) => (
          <li
            key={m.id}
            className="border-b border-divider [&:hover]:bg-[var(--mem-hover)]"
            style={{
              paddingTop: 'var(--mem-item-pad-y)',
              paddingBottom: 'var(--mem-item-pad-y)',
            }}
          >
            {/* A data é ancorada na borda direita do bloco, não colada no fim
                do texto: na referência ela forma uma coluna própria, alinhada
                entre todos os itens, independente do tamanho de cada texto. */}
            <div className="flex items-start gap-lg">
              {/* O teto de largura é medido: sem ele o texto se espalha até a
                  coluna da data e o item que na referência ocupa 2 linhas passa
                  a caber em 1, mudando a altura de toda a lista. */}
              <p
                className="flex-1 text-text-primary"
                style={{
                  fontSize: 'var(--mem-item-texto)',
                  lineHeight: 'var(--mem-item-lh)',
                  maxWidth: 'var(--mem-texto-max)',
                }}
              >
                {m.texto}
              </p>
              <span
                className="text-text-secondary shrink-0 whitespace-nowrap ml-auto"
                style={{ fontSize: 'var(--mem-data)' }}
              >
                {quando(m.criada)}
              </span>
            </div>
            <p
              className="text-text-secondary"
              style={{ fontSize: 'var(--mem-origem)', marginTop: 'var(--mem-origem-top)' }}
            >
              de: {m.tema}
            </p>
          </li>
        ))}
      </ul>

      {/* Texto de referencias/telas/10-memoria-vazio.png. */}
      {resultado?.estado === 'ok' && todas.length === 0 && (
        <EstadoVazio
          icone="memoria"
          titulo="Ainda não há nada guardado"
          corpo={'O Solis guarda o que importa das suas conversas.\nO que ele lembrar vai aparecer aqui.'}
        />
      )}
      {resultado?.estado === 'sem-servidor' && (
        <EstadoVazio
          icone="memoria"
          titulo="Servidor do Solis desligado"
          corpo={'Sem ele, o Solis não alcança as memórias guardadas.\nIniciar com npm run backend.'}
        />
      )}
    </main>
  );
}
