import type { FormEventHandler, ReactNode } from 'react';
import { alternarConversa, useConversaAtiva } from '../conversaVoz';
import { Icone } from './icons';

/** A caixa de escrever do visual novo, a mesma na Conversa vazia e na thread.
 *
 *  PROVISÓRIO — desenho próprio (27/11/2026), a direção "B com o melhor da C"
 *  que o Matheus escolheu no canvas: a caixa de duas linhas do Claude (o campo
 *  em cima, os controles embaixo, a seta num círculo de accent) e, da C, o botão
 *  grande da voz ao lado. Medidas em layout.visualNovo.composer e .voz.
 *
 *  A caixa fica no eixo da conversa: à esquerda há uma célula vazia da largura
 *  do botão da voz, pra que o botão à direita não empurre a caixa pra fora do
 *  centro (o mesmo eixo das mensagens). Na tela estreita a célula some. */
export function CaixaEscrever({
  campo,
  esquerda,
  direita,
  aoEnviar,
  acima,
}: {
  /** O campo de texto (input), com o próprio estado. */
  campo: ReactNode;
  /** Os controles da esquerda (anexar, pesquisa, privado...). */
  esquerda?: ReactNode;
  /** Os da direita (o cérebro, o ditado, a seta). */
  direita: ReactNode;
  aoEnviar: FormEventHandler<HTMLFormElement>;
  /** O que vai logo acima da caixa, na largura dela (os anexos, a barra do projeto). */
  acima?: ReactNode;
}) {
  return (
    <div className="caixa-escrever">
      <span aria-hidden className="caixa-vazio" />
      {acima && <div className="caixa-acima">{acima}</div>}
      <form
        className="composer-solis flex flex-col min-w-0"
        style={{
          background: 'var(--vn-caixa-fundo)',
          border: '1px solid var(--vn-caixa-borda)',
          borderRadius: 'var(--vn-caixa-raio)',
          boxShadow: 'var(--vn-caixa-sombra)',
          padding: 'var(--vn-caixa-pt) var(--vn-caixa-pr) var(--vn-caixa-pb) var(--vn-caixa-pl)',
          gap: 'var(--vn-caixa-gap)',
        }}
        onSubmit={aoEnviar}
      >
        {campo}
        <div className="flex items-center justify-between" style={{ gap: 8, marginLeft: -8 }}>
          <div className="flex items-center min-w-0" style={{ gap: 2 }}>
            {esquerda}
          </div>
          <div className="flex items-center shrink-0" style={{ gap: 6 }}>
            {direita}
          </div>
        </div>
      </form>
      <BotaoVoz />
    </div>
  );
}

/** O botão grande da voz: entra no modo Conversa (falar e ouvir, conversaVoz.ts),
 *  ou sai se já estiver nele. O ícone é o das ondas, o do BotaoConversa aprovado
 *  em 17/11/2026 (o do modo de voz do Claude); o microfone dentro da caixa
 *  continua sendo o ditado. Anel e brilho parados: nada animado em box-shadow
 *  (docs/PERFORMANCE.md). */
export function BotaoVoz() {
  const ativa = useConversaAtiva();
  return (
    <button
      type="button"
      onClick={alternarConversa}
      className="caixa-voz bg-accent text-canvas flex items-center justify-center shrink-0 self-center"
      style={{
        width: 'var(--vn-voz)',
        height: 'var(--vn-voz)',
        borderRadius: 999,
        boxShadow: ativa
          ? '0 0 0 8px var(--vn-voz-brilho), 0 10px 30px var(--vn-voz-brilho)'
          : '0 0 0 8px var(--vn-voz-anel), 0 10px 30px var(--vn-voz-brilho)',
      }}
      aria-label={ativa ? 'Sair da conversa por voz' : 'Falar com o Solis'}
      title={ativa ? 'Sair da conversa por voz (Esc)' : 'Falar com o Solis (conversa por voz)'}
      aria-pressed={ativa}
    >
      <Icone nome="ondas" tamanho="var(--vn-voz-icone)" />
    </button>
  );
}

/** Um botão de ícone da caixa (anexar, o ditado): o alvo de 34 com o ícone de 18. */
export const estiloBotaoCaixa = {
  width: 'var(--vn-caixa-alvo)',
  height: 'var(--vn-caixa-alvo)',
  borderRadius: 10,
} as const;

/** A seta (ou o parar, enquanto responde): o círculo de accent de 36, como no Claude. */
export function BotaoEnviar({
  parar,
  desligado,
  aoParar,
}: {
  /** Respondendo: vira o parar (o quadrado), se der pra parar. */
  parar?: boolean;
  desligado?: boolean;
  aoParar?: () => void;
}) {
  return (
    <button
      type={parar ? 'button' : 'submit'}
      onClick={parar ? aoParar : undefined}
      className="bg-accent text-canvas flex items-center justify-center shrink-0"
      style={{ width: 'var(--vn-enviar)', height: 'var(--vn-enviar)', borderRadius: 999, opacity: desligado ? 0.4 : 1 }}
      aria-label={parar ? 'Parar a resposta' : 'Enviar'}
      aria-disabled={desligado || undefined}
    >
      <Icone nome={parar ? 'parar' : 'enviar'} tamanho="var(--vn-caixa-icone)" />
    </button>
  );
}
