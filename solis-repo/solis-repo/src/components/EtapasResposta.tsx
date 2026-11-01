import { useEffect, useState } from 'react';
import { depois, duracao, passos, segundos, type EtapaRecebida, type Passo } from '../etapas';
import { Icone } from './icons';

/** O que o Solis está fazendo enquanto responde, e o que fez depois.
 *  Referência: referencias/telas/20-conversa-etapas.png; medidas em
 *  layout.thread.etapas (solis-tokens.json).
 *
 *  Três peças, cada uma num lugar da thread:
 *    - `ListaEtapas`: as etapas com check, a atual com ponto e as futuras com
 *      anel — embaixo do cabeçalho, enquanto ainda não há texto;
 *    - `DobraEtapas`: a linha recolhida "4 etapas · 3,1 s" ACIMA do cabeçalho,
 *      depois que o texto começou; abre a lista;
 *    - `AvisosDepois`: os chips de "Memória guardada" embaixo da resposta. */

/** O relógio da etapa atual anda de segundo em segundo enquanto há etapa viva.
 *  É estado, não animação: um re-render por segundo, nada em loop no CSS. */
function useAgora(ativo: boolean) {
  const [agora, definir] = useState(Date.now());
  useEffect(() => {
    if (!ativo) return;
    const id = setInterval(() => definir(Date.now()), 1000);
    return () => clearInterval(id);
  }, [ativo]);
  return agora;
}

function Marca({ estado }: { estado: Passo['estado'] }) {
  // Caixa de 16px a 3px da coluna: o check ocupa ela inteira, ponto e anel
  // ficam no centro dela (x 391,5 da referência, os três alinhados).
  return (
    <span className="shrink-0 flex items-center justify-center" style={{ width: 'var(--et-icone)', marginLeft: 3 }}>
      {estado === 'feita' && <Icone nome="feito" tamanho="var(--et-icone)" className="text-accent" />}
      {estado === 'atual' && (
        <span className="bg-accent" style={{ width: 'var(--et-ponto)', height: 'var(--et-ponto)', borderRadius: 999 }} />
      )}
      {(estado === 'futura' || estado === 'falhou') && (
        <span
          style={{
            width: 'var(--et-anel)',
            height: 'var(--et-anel)',
            borderRadius: 999,
            border: '1.5px solid var(--text-secondary)',
            opacity: 'var(--et-futura)',
          }}
        />
      )}
    </span>
  );
}

const COR: Record<Passo['estado'], string> = {
  feita: 'text-text-secondary',
  atual: 'text-text-primary',
  futura: 'text-text-secondary',
  // PROVISÓRIO: a referência não mostra cérebro que falhou. Anel de futura e
  // texto secundário: aconteceu, mas não com check — não deu certo.
  falhou: 'text-text-secondary',
};

export function ListaEtapas({ etapas, vivo }: { etapas: EtapaRecebida[]; vivo: boolean }) {
  // O tique só provoca o re-render; a conta usa a hora de agora, porque uma
  // etapa que chegou entre dois tiques é mais nova que o último tique.
  useAgora(vivo);
  return (
    <ol aria-label="Etapas da resposta" aria-live="polite">
      {passos(etapas, vivo, Date.now()).map((p, i) => (
        <li
          key={i}
          className={`flex items-center ${COR[p.estado]}`}
          style={{ height: 'var(--et-passo)', fontSize: 'var(--et-texto)' }}
        >
          <Marca estado={p.estado} />
          <span
            style={{
              marginLeft: 'calc(var(--et-recuo) - var(--et-icone) - 3px)',
              opacity: p.estado === 'futura' ? 'var(--et-futura)' : undefined,
            }}
          >
            {p.texto}
          </span>
        </li>
      ))}
    </ol>
  );
}

export function DobraEtapas({
  etapas,
  vivo,
  aberta,
  aoAlternar,
}: {
  etapas: EtapaRecebida[];
  vivo: boolean;
  aberta: boolean;
  aoAlternar: () => void;
}) {
  const feitas = passos(etapas, false).length;
  return (
    <button
      type="button"
      onClick={aoAlternar}
      aria-expanded={aberta}
      // Alinhada pelo topo, numa caixa da altura do passo até o cabeçalho: o
      // topo dos números fica a 29px do topo da caixa alta da hora, como os
      // 40px da imagem. Centralizada, sobravam 24.
      className="relative flex items-start text-text-secondary"
      style={{ height: 'var(--et-dobra-gap)', fontSize: 'var(--et-dobra-texto)', paddingLeft: 'var(--et-dobra-recuo)' }}
    >
      {/* O chevron de 16px tem 3px de folga no grid; recuado 3px, a tinta
          encosta na coluna como na referência. O meio da tinta dele cai no
          meio dos números. Aberta, aponta pra cima. */}
      <Icone
        nome="chevron"
        tamanho={16}
        className="absolute"
        style={{ left: -3, top: 0, transform: aberta ? 'rotate(180deg)' : undefined }}
      />
      {feitas} {feitas === 1 ? 'etapa' : 'etapas'} · {segundos(duracao(etapas))}
      {vivo && '…'}
    </button>
  );
}

export function AvisosDepois({ etapas }: { etapas: EtapaRecebida[] }) {
  const avisos = depois(etapas);
  if (!avisos.length) return null;
  return (
    <div className="flex flex-col items-start" style={{ marginTop: 'var(--et-chip-top)', gap: 8 }}>
      {avisos.map((a) => (
        <span
          key={a}
          title={a}
          className="inline-flex items-center text-text-primary"
          style={{
            // Uma memória longa (o pedido cru, quando o modelo não extraiu) não
            // passa da coluna de leitura: corta com reticências, e o texto
            // inteiro fica no title e na tela de Memória.
            maxWidth: 'var(--th-texto-max)',
            height: 'var(--et-chip-h)',
            padding: '0 var(--et-chip-px)',
            gap: 'var(--et-chip-icone-gap)',
            fontSize: 'var(--et-chip-texto)',
            borderRadius: 'var(--et-chip-raio)',
            border: '1px solid color-mix(in srgb, var(--accent) var(--et-chip-borda), transparent)',
            background: 'color-mix(in srgb, var(--accent) var(--et-chip-fundo), transparent)',
          }}
        >
          <Icone nome="feito" tamanho={14} className="text-accent shrink-0" />
          <span className="truncate">{a}</span>
        </span>
      ))}
    </div>
  );
}
