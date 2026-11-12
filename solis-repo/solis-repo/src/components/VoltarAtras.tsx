import { useEffect, useState } from 'react';
import { nomeDoArquivo } from '../etapas';
import { voltarAtras, type Volta } from '../servidor';
import { Botao } from './Controles';

/** Voltar atrás, embaixo de uma fala da pessoa: o que o Claude mudou nos
 *  arquivos dela em diante volta a como estava antes dela — e, se o Matheus
 *  quiser, a conversa volta junto (a fala vai pro campo de novo, como no
 *  /rewind do Claude Code). Antes de voltar, mostra o que volta.
 *
 *  PROVISÓRIO — desenho próprio (12/11/2026), base no Claude Code: o cartão
 *  de aprovação (--et-apr-*) com a borda neutra (layout.thread.etapas._rewind
 *  no solis-tokens.json). Precisa do aval do Matheus nos 3 temas e 2 navs. */

type Estado =
  | { tipo: 'vendo' }
  | { tipo: 'pronto'; volta: Volta }
  | { tipo: 'voltando'; volta: Volta }
  | { tipo: 'feito'; volta: Volta }
  | { tipo: 'erro'; texto: string };

const linhas = (n: number) => `${n} ${n === 1 ? 'linha' : 'linhas'}`;

/** As linhas que o voltar mexe, contadas pelo CLI do lado da volta: o que o
 *  Claude acrescentou sai, o que ele tirou volta. Sem a parte que é zero. */
function oQueMuda(v: Volta, feito: boolean): string {
  const partes = [];
  if (v.menos) partes.push(`${linhas(v.menos)} ${feito ? (v.menos === 1 ? 'saiu' : 'saíram') : v.menos === 1 ? 'sai' : 'saem'}`);
  if (v.mais) partes.push(`${linhas(v.mais)} ${feito ? (v.mais === 1 ? 'voltou' : 'voltaram') : v.mais === 1 ? 'volta' : 'voltam'}`);
  const frase = partes.join(' e ');
  return frase ? frase.charAt(0).toUpperCase() + frase.slice(1) + '.' : '';
}

export function VoltarAtras({
  conversa,
  desde,
  aoFechar,
  aoVoltar,
}: {
  conversa: number;
  /** A fala da pessoa (o id no banco). */
  desde: number;
  aoFechar: () => void;
  /** Voltou. `comConversa`: a fala e o que veio depois saíram do banco. */
  aoVoltar: (comConversa: boolean) => void;
}) {
  const [estado, definirEstado] = useState<Estado>({ tipo: 'vendo' });

  useEffect(() => {
    let vivo = true;
    voltarAtras(conversa, desde, { simular: true }).then((r) => {
      if (!vivo) return;
      if (r === 'respondendo') definirEstado({ tipo: 'erro', texto: 'Espere a resposta acabar pra voltar atrás.' });
      else if (!r) definirEstado({ tipo: 'erro', texto: 'Não consegui falar com o servidor do Solis.' });
      else definirEstado({ tipo: 'pronto', volta: r });
    });
    return () => {
      vivo = false;
    };
  }, [conversa, desde]);

  const voltar = async (comConversa: boolean) => {
    if (estado.tipo !== 'pronto') return;
    definirEstado({ tipo: 'voltando', volta: estado.volta });
    const r = await voltarAtras(conversa, desde, { conversa: comConversa });
    if (r === 'respondendo') return definirEstado({ tipo: 'erro', texto: 'Espere a resposta acabar pra voltar atrás.' });
    if (!r) return definirEstado({ tipo: 'erro', texto: 'Não consegui voltar: o servidor do Solis não respondeu.' });
    if (r.erros.length) return definirEstado({ tipo: 'erro', texto: `Não voltou tudo: ${r.erros.join('; ')}` });
    definirEstado({ tipo: 'feito', volta: r });
    aoVoltar(comConversa);
  };

  const volta = 'volta' in estado ? estado.volta : null;
  const nada = volta && !volta.arquivos.length;
  const texto = { fontSize: 'var(--et-dobra-texto)' } as const;

  return (
    <div
      role="group"
      aria-label="Voltar atrás"
      className="border border-divider"
      style={{
        width: 'min(100%, var(--th-balao-max))',
        marginTop: 8,
        padding: 'var(--et-apr-py) var(--et-apr-px)',
        borderRadius: 'var(--et-apr-raio)',
      }}
    >
      <div className="text-text-primary" style={{ fontSize: 'var(--et-texto)' }}>
        {estado.tipo === 'feito'
          ? `Voltaram ${estado.volta.arquivos.length} ${estado.volta.arquivos.length === 1 ? 'arquivo' : 'arquivos'}`
          : 'Voltar os arquivos a antes desta mensagem'}
      </div>

      {estado.tipo === 'vendo' && (
        <div className="text-text-secondary" style={{ ...texto, marginTop: 6 }}>
          Vendo o que o Claude mudou…
        </div>
      )}
      {estado.tipo === 'erro' && (
        <div className="text-[var(--erro)]" style={{ ...texto, marginTop: 6 }}>
          {estado.texto}
        </div>
      )}
      {nada && (
        <div className="text-text-secondary" style={{ ...texto, marginTop: 6 }}>
          Os arquivos já estão como antes desta mensagem.
        </div>
      )}
      {volta && !nada && (
        <>
          <ul className="font-mono text-text-primary" style={{ ...texto, marginTop: 8, lineHeight: 1.6 }}>
            {volta.arquivos.map((a) => (
              <li key={a} title={a} className="truncate">
                {nomeDoArquivo(a)}
              </li>
            ))}
          </ul>
          <div className="text-text-secondary" style={{ ...texto, marginTop: 6 }}>
            {oQueMuda(volta, estado.tipo === 'feito')}
            {estado.tipo !== 'feito' && ' Os comandos que o Claude rodou não voltam.'}
          </div>
        </>
      )}

      <div className="flex justify-end flex-wrap" style={{ gap: 'var(--mac-botao-gap)', marginTop: 12 }}>
        {estado.tipo === 'pronto' && !nada ? (
          <>
            <Botao onClick={aoFechar}>Cancelar</Botao>
            <Botao onClick={() => voltar(false)}>Só os arquivos</Botao>
            <Botao tipo="destaque" onClick={() => voltar(true)}>
              Arquivos e conversa
            </Botao>
          </>
        ) : (
          <Botao onClick={aoFechar} disabled={estado.tipo === 'voltando'}>
            {estado.tipo === 'voltando' ? 'Voltando…' : 'Fechar'}
          </Botao>
        )}
      </div>
    </div>
  );
}
