import { useEffect, useRef, useState } from 'react';
import { Botao } from '../components/Controles';
import { Icone } from '../components/icons';
import { amostraFish, listarVozesFish, type VozFish } from '../servidor';

/** A biblioteca de vozes da Fish, pra achar a voz do Solis (pedido do Matheus,
 *  11/11/2026: "mais vozes, uma que faça mais sentido com o Solis").
 *
 *  Busca pelo nome, filtros pelas etiquetas da própria Fish, português ou
 *  todas as línguas, e "Mais vozes" de 20 em 20. O "Ouvir" fala a MESMA frase
 *  do Solis em toda voz (pelo modelo grátis), pra comparar de igual pra igual —
 *  a amostra de cada autor diz coisas diferentes.
 *
 *  PROVISÓRIO — desenho próprio, com as peças do cartão de Voz: o campo de
 *  texto e o botão do cartão Cérebros, o "Ouvir" das linhas, o hover das listas
 *  da Memória (--mem-hover). Precisa do aval do Matheus pelos prints. */

const ETIQUETAS: [string, string][] = [
  ['', 'Todas'],
  ['male', 'Masculinas'],
  ['female', 'Femininas'],
  ['calm', 'Calmas'],
  ['conversational', 'De conversa'],
  ['narration', 'Narração'],
  ['deep', 'Graves'],
];

const ORDENS: [string, string][] = [
  ['score', 'Melhores'],
  ['task_count', 'Mais usadas'],
  ['created_at', 'Mais novas'],
];

const mil = (n: number) =>
  n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1).replace('.', ',')} mi` : n >= 1000 ? `${Math.round(n / 1000)} mil` : String(n);

export function VozesFish({ emUso, aoUsar }: { emUso: string | null; aoUsar: (voz: VozFish) => void }) {
  // Começa em "assistente": vazia, a ordem da Fish abre nos clones de famosos
  // (os mais populares) — visto no teste com a biblioteca de verdade.
  const [busca, definirBusca] = useState('assistente');
  const [etiqueta, definirEtiqueta] = useState('');
  const [ordem, definirOrdem] = useState('score');
  const [soPortugues, definirSoPortugues] = useState(true);
  const [vozes, definirVozes] = useState<VozFish[]>([]);
  const [pagina, definirPagina] = useState(1);
  const [temMais, definirTemMais] = useState(false);
  const [carregando, definirCarregando] = useState(false);
  const [erro, definirErro] = useState(false);
  const [ouvindo, definirOuvindo] = useState<string | null>(null);
  const [tempo, definirTempo] = useState<Record<string, number>>({});
  const tocando = useRef<HTMLAudioElement | null>(null);
  const pedido = useRef(0);

  // Busca nova (filtro, ordem, texto): volta pra primeira página. O texto
  // espera a pessoa parar de digitar.
  useEffect(() => {
    const meu = ++pedido.current;
    const id = window.setTimeout(
      async () => {
        definirCarregando(true);
        const r = await listarVozesFish({ busca, pagina: 1, ordem, lingua: soPortugues ? 'pt' : '', etiqueta });
        if (meu !== pedido.current) return;
        definirCarregando(false);
        definirErro(!r);
        definirVozes(r?.vozes ?? []);
        definirTemMais(!!r?.tem_mais);
        definirPagina(1);
      },
      busca ? 400 : 0,
    );
    return () => window.clearTimeout(id);
  }, [busca, etiqueta, ordem, soPortugues]);

  useEffect(() => () => tocando.current?.pause(), []);

  async function mais() {
    const meu = ++pedido.current;
    definirCarregando(true);
    const r = await listarVozesFish({ busca, pagina: pagina + 1, ordem, lingua: soPortugues ? 'pt' : '', etiqueta });
    if (meu !== pedido.current) return;
    definirCarregando(false);
    if (!r) return definirErro(true);
    // A Fish pode repetir uma voz entre páginas: sem duplicata na lista.
    definirVozes((vs) => [...vs, ...r.vozes.filter((v) => !vs.some((x) => x.id === v.id))]);
    definirTemMais(r.tem_mais);
    definirPagina((p) => p + 1);
  }

  async function ouvir(v: VozFish) {
    tocando.current?.pause();
    if (ouvindo === v.id) return definirOuvindo(null);
    definirOuvindo(v.id);
    const r = await amostraFish(v.id);
    if (!r || r === 'sem-voz') return definirOuvindo(null);
    definirTempo((t) => ({ ...t, [v.id]: r.segundos }));
    const url = URL.createObjectURL(r.audio);
    const el = new Audio(url);
    tocando.current = el;
    el.onended = el.onerror = () => {
      URL.revokeObjectURL(url);
      definirOuvindo((o) => (o === v.id ? null : o));
    };
    el.play().catch(() => definirOuvindo(null));
  }

  const chip = (ativo: boolean) =>
    `border ${ativo ? 'border-[color-mix(in_srgb,var(--accent)_55%,transparent)] text-text-primary bg-[color-mix(in_srgb,var(--accent)_8%,transparent)]' : 'border-divider text-text-secondary hover:text-text-primary'}`;

  return (
    <div style={{ paddingBottom: 'var(--cfg-linha-pad)' }}>
      <div className="flex items-center flex-wrap" style={{ gap: 'var(--mac-botao-gap)' }}>
        <input
          value={busca}
          onChange={(e) => definirBusca(e.target.value)}
          placeholder="Buscar voz pelo nome (assistente, narrador, calma…)"
          aria-label="Buscar voz da Fish"
          className="flex-1 bg-transparent outline-none text-text-primary placeholder:text-text-secondary border border-divider focus:border-[color-mix(in_srgb,var(--accent)_55%,transparent)]"
          style={{
            minWidth: 240,
            fontSize: 'var(--cfg-dica)',
            borderRadius: 'var(--mac-campo-raio)',
            padding: 'var(--mac-campo-py) var(--mac-campo-px)',
          }}
        />
        <button
          type="button"
          onClick={() => definirSoPortugues((s) => !s)}
          aria-pressed={soPortugues}
          className={chip(soPortugues)}
          style={{ height: 'var(--mac-botao-h)', padding: '0 var(--mac-botao-px)', borderRadius: 'var(--mac-botao-raio)', fontSize: 'var(--mac-botao-texto)' }}
        >
          Só português
        </button>
        <select
          value={ordem}
          onChange={(e) => definirOrdem(e.target.value)}
          aria-label="Ordem das vozes"
          className="solis-data bg-canvas text-text-secondary border border-divider outline-none"
          style={{ height: 'var(--mac-botao-h)', padding: '0 var(--mac-campo-px)', borderRadius: 'var(--mac-botao-raio)', fontSize: 'var(--mac-botao-texto)' }}
        >
          {ORDENS.map(([v, r]) => (
            <option key={v} value={v}>
              {r}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-wrap" role="group" aria-label="Tipo de voz" style={{ gap: 6, marginTop: 'var(--mac-botao-gap)' }}>
        {ETIQUETAS.map(([v, r]) => (
          <button
            key={v}
            type="button"
            onClick={() => definirEtiqueta(v)}
            aria-pressed={etiqueta === v}
            className={chip(etiqueta === v)}
            style={{ height: 28, padding: '0 12px', borderRadius: 999, fontSize: 'var(--et-chip-texto)' }}
          >
            {r}
          </button>
        ))}
      </div>

      <p className="text-text-secondary" style={{ fontSize: 'var(--et-chip-texto)', marginTop: 'var(--mac-botao-gap)', maxWidth: 'var(--cer-texto-max)' }}>
        Muitas vozes da biblioteca imitam pessoas reais ou personagens. Pro Solis, prefira as feitas pra assistente: a
        voz de alguém sem a autorização dele não pode ir pra um produto.
      </p>

      <ul aria-label="Vozes da Fish" aria-busy={carregando} style={{ marginTop: 'var(--mac-botao-gap)' }}>
        {vozes.map((v) => {
          const usada = v.id === emUso;
          return (
            <li
              key={v.id}
              className="flex items-center hover:bg-[var(--mem-hover)]"
              style={{ gap: 'var(--mac-botao-gap)', padding: '10px 12px', margin: '0 -12px', borderRadius: 'var(--mac-campo-raio)' }}
            >
              <button
                type="button"
                onClick={() => ouvir(v)}
                title="Ouvir a frase do Solis nesta voz"
                aria-label={`Ouvir a voz ${v.nome}`}
                className={`flex items-center justify-center shrink-0 ${ouvindo === v.id ? 'text-accent solis-ouvindo' : 'text-text-secondary hover:text-text-primary'}`}
                style={{ width: 'var(--mac-alvo)', height: 'var(--mac-alvo)', borderRadius: 'var(--mac-botao-raio)' }}
              >
                <Icone nome="fala" tamanho="var(--mac-icone)" />
              </button>
              <div className="flex-1 min-w-0">
                <div className="text-text-primary truncate" style={{ fontSize: 'var(--cfg-rotulo)' }}>
                  {v.nome}
                </div>
                {v.descricao && (
                  <div className="text-text-secondary truncate" title={v.descricao} style={{ fontSize: 'var(--cfg-dica)' }}>
                    {v.descricao}
                  </div>
                )}
                <div className="text-text-secondary" style={{ fontSize: 'var(--et-chip-texto)', marginTop: 2 }}>
                  {mil(v.usos)} usos · {mil(v.curtidas)} curtidas
                  {v.linguas.length > 0 && ` · ${v.linguas.join(', ')}`}
                  {tempo[v.id] !== undefined && ` · falou em ${tempo[v.id].toFixed(1).replace('.', ',')} s`}
                </div>
              </div>
              {usada ? (
                <span className="text-accent shrink-0" style={{ fontSize: 'var(--mac-botao-texto)', padding: '0 var(--mac-botao-px)' }}>
                  Em uso
                </span>
              ) : (
                <Botao onClick={() => aoUsar(v)}>Usar</Botao>
              )}
            </li>
          );
        })}
      </ul>

      {!carregando && !erro && vozes.length === 0 && (
        <p className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)' }}>
          Nenhuma voz com esse nome. Tente outra palavra, ou "Todas" as línguas.
        </p>
      )}
      {erro && (
        <p className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)' }}>
          Não consegui falar com a Fish agora. Tente de novo em instantes.
        </p>
      )}
      {temMais && (
        <div style={{ marginTop: 'var(--mac-botao-gap)' }}>
          <Botao onClick={mais} disabled={carregando}>
            {carregando ? 'Carregando…' : 'Mais vozes'}
          </Botao>
        </div>
      )}
    </div>
  );
}
