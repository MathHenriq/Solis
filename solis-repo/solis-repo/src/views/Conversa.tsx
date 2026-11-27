import { BotaoCadeado } from '../components/BotaoCadeado';
import { useRef, useState } from 'react';
import { BotaoMicrofone } from '../components/BotaoMicrofone';
import { BotaoEnviar, CaixaEscrever } from '../components/CaixaEscrever';
import { Icone, type NomeIcone } from '../components/icons';
import { falaAutomatica, marcarRespostaFalada } from '../fala';
import { useVoz } from '../voz';

/** Tela de Conversa — estado de abertura.
 *
 *  Medidas de docs/MEDICOES_FASE2.md, normalizadas pra janela de 1440px.
 *  Referências: referencias/telas/tema-dark.png, tema-espacial-vinho.png,
 *  tema-claro-padrao.png (as 3 mostram esta mesma tela).
 *
 *  O microfone está aqui porque a decisão registrada é que ele sumiu das 3
 *  telas por omissão do gerador de imagem, não por decisão de produto: Whisper
 *  e a Camada 3 do SOLIS_SIGNATURE.md dependem dele como porta de entrada. */

const ATALHOS: { rotulo: string; icone: NomeIcone }[] = [
  { rotulo: 'Nova tarefa', icone: 'nova-tarefa' },
  { rotulo: 'Buscar algo', icone: 'buscar' },
  { rotulo: 'Resumir', icone: 'resumir' },
  { rotulo: 'Analisar', icone: 'analisar' },
];

export function Conversa({
  aoEnviar,
  ouvindo = false,
}: { aoEnviar?: (texto: string, privada?: boolean) => void; ouvindo?: boolean } = {}) {
  const [rascunho, definirRascunho] = useState('');
  const campo = useRef<HTMLInputElement>(null);
  const ditado = useRef(false);
  // A fala transcrita entra na caixa (depois do que já estava escrito), e a
  // pessoa confere antes de enviar. Mensagem ditada tem a resposta falada.
  // O cadeado (BotaoCadeado): a primeira mensagem também pode ser privada.
  const [privado, definirPrivado] = useState(false);
  const privadoAgora = useRef(false);
  privadoAgora.current = privado;
  const voz = useVoz((texto) => {
    definirRascunho((r) => (r.trim() ? `${r.trimEnd()} ${texto}` : texto));
    ditado.current = true;
    campo.current?.focus();
  }, () => privadoAgora.current);
  return (
    <main className="tela-conversa relative flex-1 overflow-y-auto" style={{ zIndex: 1 }}>
      {/* 191px da divisória da sidebar. O topo é 298 e não 295 porque a Playfair
          tem métrica diferente da serifada genérica que estava antes: a mesma caixa
          punha a tinta 3px mais alto. Esses 298 são o TETO: numa janela de 930 de
          altura é exatamente o que sai; numa de 693, que é o que um navegador dá,
          298 seriam 43% da altura e jogavam o bloco inteiro pra metade de baixo,
          espremendo o horizonte. Ver layout.escalaVertical. */}
      {/* No modo 'icones' não há sidebar, e a referência mostra a coluna
          centralizada na janela em vez de encostada à esquerda. A troca é só de
          CSS, por atributo na raiz — o componente não precisa saber do modo. */}
      {/* A coluna acompanha a largura do composer. Sem isso os chips e o campo
          ficavam com medidas independentes, e numa janela larga um esticava e o
          outro não — que é o tipo de desalinho que só aparece fora dos 1440px em
          que a referência foi medida. */}
      {/* Nenhuma geometria aqui: largura, âncora, teto e o topo vivem todos no
          CSS (.conversa-coluna em index.css). O topo estava neste style inline, e
          inline vence qualquer seletor — então a regra do modo 'icones', que
          precisa zerar o topo pra centralizar o bloco na faixa, era silenciosamente
          ignorada. */}
      <div className="conversa-coluna">
        <h1 className="font-display text-hero text-text-primary leading-none">Olá, Matheus.</h1>

        {/* subtítulo a 359px do topo */}
        <p className="text-text-secondary" style={{ marginTop: 'var(--conversa-sub)', fontSize: 20 }}>
          Como posso te ajudar hoje?
        </p>

        {/* A caixa de escrever do visual novo (CaixaEscrever.tsx, PROVISÓRIO
            27/11/2026): a mesma da thread, com o botão grande da voz ao lado.
            Aqui só o privado à esquerda e o ditado e a seta à direita — anexo,
            pesquisa e o cérebro entram quando a conversa já está aberta. */}
        <div style={{ marginTop: 'var(--conversa-campo)' }}>
          <CaixaEscrever
            aoEnviar={(e) => {
              e.preventDefault();
              // A primeira mensagem é o que abre a thread — o shell troca de
              // estado assim que a conversa deixa de estar vazia.
              if (!rascunho.trim()) return;
              marcarRespostaFalada(ditado.current && falaAutomatica());
              aoEnviar?.(rascunho, privado);
            }}
            campo={
              <input
                ref={campo}
                value={rascunho}
                onChange={(e) => definirRascunho(e.target.value)}
                className={`w-full bg-transparent outline-none text-text-primary ${voz.erro ? 'placeholder:text-[var(--erro)]' : 'placeholder:text-text-placeholder'}`}
                style={{ fontSize: 'var(--vn-caixa-texto)', padding: '4px 0' }}
                placeholder={ouvindo ? 'Ouvindo… pode falar' : voz.dica ?? 'Fale com o Solis…'}
                aria-label="Fale com o Solis"
              />
            }
            esquerda={<BotaoCadeado ligado={privado} aoTrocar={definirPrivado} tamanho={18} />}
            direita={
              <>
                <BotaoMicrofone estado={ouvindo ? 'ouvindo' : voz.estado} aoClicar={voz.alternar} tamanho={18} />
                <BotaoEnviar desligado={!rascunho.trim()} />
              </>
            }
          />
        </div>

        {/* chips 34px abaixo do composer, altura 56, vão de 22 */}
        <div className="flex" style={{ marginTop: 'var(--conversa-chips)', gap: 18 }}>
          {ATALHOS.map((a) => (
            <button
              key={a.rotulo}
              type="button"
              // Superfície própria em vez de fundo transparente: sobre a foto
              // do horizonte o contorno fino sozinho sumia e o texto flutuava.
              // O véu é o do canvas, então não opaca a foto atrás.
              className="flex items-center gap-md border border-divider rounded-md text-text-primary
                         bg-[var(--mem-hover)] hover:bg-[var(--mem-hover-forte)]"
              style={{
                height: 'var(--chip-height)',
                paddingLeft: 18,
                paddingRight: 19,
                fontSize: 'var(--chip-texto)',
              }}
            >
              <span className="text-accent"><Icone nome={a.icone} tamanho={17} /></span>
              {a.rotulo}
            </button>
          ))}
        </div>
      </div>
    </main>
  );
}
