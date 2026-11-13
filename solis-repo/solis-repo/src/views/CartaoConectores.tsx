import { useEffect, useState } from 'react';
import { listarConectores, type Conector } from '../servidor';

/** Configurações → Conectores: os conectores da conta do claude.ai (Agenda,
 *  Drive, Canva...) que o Claude do Solis usa — como Configurações →
 *  Conectores no Claude Desktop. Ligar um novo e entrar num que pede é no
 *  claude.ai: o Solis usa os da conta, não guarda senha de ninguém.
 *
 *  PROVISÓRIO — desenho próprio (13/11/2026): o cartão e as linhas do de
 *  Cérebros (layout.configuracoes.cerebros, aprovado em 08/11/2026), só texto,
 *  sem controles. Precisa do aval do Matheus nos 3 temas e 2 navs. */

function estadoDe(c: Conector): string {
  switch (c.estado) {
    case 'conectado':
      return `Conectado · ${c.ferramentas} ${c.ferramentas === 1 ? 'ferramenta' : 'ferramentas'}` +
        (c.so_leem ? `, ${c.so_leem} só ${c.so_leem === 1 ? 'lê' : 'leem'}` : '');
    case 'precisa_entrar':
      return 'Precisa entrar: no claude.ai, em Configurações → Conectores.';
    case 'conectando':
      return 'Conectando…';
    default:
      return 'Não respondeu agora.';
  }
}

export function CartaoConectores() {
  // undefined = lendo; null = não deu.
  const [lista, definirLista] = useState<Conector[] | null | undefined>(undefined);

  const ler = (atualizar = false) => {
    definirLista(undefined);
    void listarConectores(atualizar).then(definirLista);
  };
  useEffect(() => ler(), []);

  return (
    <section
      className="border border-divider"
      style={{
        marginTop: 'var(--cer-cartao-gap)',
        marginBottom: 'var(--cer-cartao-gap)',
        borderRadius: 'var(--cfg-card-raio)',
        padding: 'var(--cfg-card-pad)',
      }}
    >
      <div className="flex items-start justify-between" style={{ gap: 'var(--cer-controles-gap)' }}>
        <h2 className="text-text-primary" style={{ fontSize: 'var(--cfg-secao)' }}>Conectores</h2>
        <button
          type="button"
          onClick={() => ler(true)}
          disabled={lista === undefined}
          className="text-text-secondary hover:text-text-primary hover:underline disabled:opacity-50 shrink-0"
          style={{ fontSize: 'var(--cfg-dica)' }}
        >
          Ver de novo
        </button>
      </div>
      <p
        className="text-text-secondary"
        style={{ fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)', maxWidth: 'var(--cer-texto-max)', textWrap: 'pretty' }}
      >
        Os da sua conta do claude.ai, que o Claude usa aqui também. Ler é livre; criar, mudar, apagar ou
        compartilhar pede você antes. Ligar um novo é no claude.ai.
      </p>

      {lista === undefined && (
        <p className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)', marginTop: 'var(--cer-linha-pad)' }}>
          Vendo os conectores da sua conta… leva alguns segundos.
        </p>
      )}
      {lista === null && (
        <p className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)', marginTop: 'var(--cer-linha-pad)' }}>
          Não consegui ver os conectores agora: o servidor do Solis ou o Claude não respondeu.
        </p>
      )}
      {lista && lista.length === 0 && (
        <p className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)', marginTop: 'var(--cer-linha-pad)' }}>
          Nenhum conector na sua conta do claude.ai.
        </p>
      )}
      {lista && lista.length > 0 && (
        <ul aria-label="Conectores">
          {lista.map((c) => (
            <li
              key={c.nome}
              className="border-t border-divider first:border-t-0"
              style={{ paddingTop: 'var(--cer-linha-pad)', paddingBottom: 'var(--cer-linha-pad)' }}
            >
              <div className="text-text-primary" style={{ fontSize: 'var(--cfg-rotulo)' }}>
                {c.nome}
              </div>
              <div
                className={c.estado === 'precisa_entrar' || c.estado === 'falhou' ? 'text-[var(--erro)]' : 'text-text-secondary'}
                style={{ fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)', maxWidth: 'var(--cer-texto-max)' }}
              >
                {estadoDe(c)}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
