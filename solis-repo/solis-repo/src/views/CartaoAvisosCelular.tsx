import { useCallback, useEffect, useState } from 'react';
import { Interruptor } from '../components/Controles';
import { desligarPush, inscricaoAtual, ligarPush, suportePush } from '../push';
import { lerPush, removerPush, testarPush, type EstadoPush } from '../servidor';

/** Configurações → Avisos no celular (backend/solis/push.py, 26/11/2026): os
 *  avisos do Solis (compromisso, tarefa, site fora do ar, as novidades da semana)
 *  como notificação do celular, pelo Web Push do navegador.
 *
 *  PROVISÓRIO: desenho próprio no molde do cartão Controle da tela; o visual é
 *  refeito no fim (sem prints até lá, regra de 21/11/2026). */

const POR_QUE_NAO: Record<string, string> = {
  app: 'No app do PC os avisos já aparecem no Windows. Pra receber no celular, abra o Solis pelo endereço do servidor no navegador do celular e ligue aqui.',
  inseguro: 'Os avisos precisam de conexão segura (https). Funciona quando o Solis estiver no servidor de verdade.',
  'iphone-fora-da-tela':
    'No iPhone, os avisos só chegam com o Solis na Tela de Início: toque em Compartilhar → Adicionar à Tela de Início e abra o Solis por lá.',
  navegador: 'Este navegador não recebe avisos. No celular, use o Chrome (Android) ou o Safari com o Solis na Tela de Início (iPhone).',
};

export function CartaoAvisosCelular() {
  const suporte = suportePush();
  const [estado, definirEstado] = useState<EstadoPush | null | undefined>(undefined);
  const [aqui, definirAqui] = useState(false);
  const [ocupado, definirOcupado] = useState(false);
  const [recado, definirRecado] = useState<{ texto: string; erro?: boolean } | null>(null);

  const ler = useCallback(async () => {
    definirEstado(await lerPush());
    definirAqui(!!(await inscricaoAtual()));
  }, []);
  useEffect(() => {
    void ler();
  }, [ler]);

  const trocar = async (ligar: boolean) => {
    definirOcupado(true);
    definirRecado(null);
    const erro = ligar ? await ligarPush() : (await desligarPush(), null);
    if (erro) definirRecado({ texto: erro, erro: true });
    await ler();
    definirOcupado(false);
  };

  const testar = async () => {
    definirRecado(null);
    const r = await testarPush();
    if (!r) definirRecado({ texto: 'O servidor do Solis não respondeu.', erro: true });
    else if (!r.aparelhos) definirRecado({ texto: 'Nenhum aparelho ligado ainda.' });
    else
      definirRecado({
        texto:
          r.entregues === r.aparelhos
            ? `Mandado ${r.aparelhos === 1 ? 'pro aparelho' : `pros ${r.aparelhos} aparelhos`}. Deve aparecer em segundos.`
            : `Chegou em ${r.entregues} de ${r.aparelhos} aparelhos; o serviço de push recusou o resto.`,
        erro: r.entregues < r.aparelhos,
      });
  };

  const tirar = async (id: string) => {
    await removerPush(id);
    await ler();
  };

  const dica = { fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)', maxWidth: 'var(--cer-texto-max)' } as const;
  const linha = { marginTop: 'var(--cer-linha-pad)', paddingTop: 'var(--cer-linha-pad)' } as const;

  return (
    <section className="cfg-cartao">
      <h2 className="text-text-primary" style={{ fontSize: 'var(--cfg-secao)' }}>Avisos no celular</h2>
      <p className="text-text-secondary" style={{ ...dica, textWrap: 'pretty' }}>
        Compromissos, tarefas, site fora do ar e as novidades da semana chegam como notificação, mesmo com o Solis
        fechado. Vão criptografados: o serviço de push do celular não lê o que diz.
      </p>

      {!suporte.pode && (
        <p className="text-text-secondary border-t border-divider" style={{ ...dica, ...linha, textWrap: 'pretty' }}>
          {POR_QUE_NAO[suporte.motivo]}
        </p>
      )}

      {suporte.pode && estado === null && (
        <p className="text-text-secondary" style={{ ...dica, ...linha }}>O servidor do Solis não respondeu.</p>
      )}

      {suporte.pode && estado && (
        <div className="flex items-center justify-between border-t border-divider" style={{ ...linha, gap: 'var(--cer-controles-gap)' }}>
          <div className="min-w-0">
            <div className="text-text-primary" style={{ fontSize: 'var(--cfg-rotulo)' }}>Receber neste aparelho</div>
            <div className="text-text-secondary" style={dica}>
              {aqui ? 'Ligado.' : 'O navegador vai pedir a permissão de notificação.'}
            </div>
          </div>
          <Interruptor ligado={aqui} rotulo="Receber os avisos neste aparelho" aoTrocar={ocupado ? undefined : (v) => void trocar(v)} />
        </div>
      )}

      {estado && estado.aparelhos.length > 0 && (
        <div className="border-t border-divider" style={linha}>
          <div className="text-text-primary" style={{ fontSize: 'var(--cfg-rotulo)' }}>Aparelhos ligados</div>
          <ul style={{ marginTop: 'var(--cfg-dica-top)' }}>
            {estado.aparelhos.map((a) => (
              <li key={a.id} className="flex items-center justify-between text-text-secondary" style={{ fontSize: 'var(--cfg-dica)', paddingBlock: 4 }}>
                <span>
                  {a.aparelho} · desde {new Date(a.criada).toLocaleDateString('pt-BR')}
                </span>
                <button type="button" className="text-text-secondary hover:text-text-primary underline" onClick={() => void tirar(a.id)}>
                  Tirar
                </button>
              </li>
            ))}
          </ul>
          <button
            type="button"
            onClick={() => void testar()}
            className="border border-[var(--vn-caixa-borda)] text-text-primary hover:bg-[var(--mem-hover)]"
            style={{ marginTop: 'var(--cfg-dica-top)', padding: '8px 14px', borderRadius: 10, fontSize: 'var(--cfg-dica)' }}
          >
            Mandar um aviso de teste
          </button>
        </div>
      )}

      {recado && (
        <div
          className={recado.erro ? 'text-[var(--erro)]' : 'text-text-secondary'}
          role={recado.erro ? 'alert' : 'status'}
          style={{ fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)' }}
        >
          {recado.texto}
        </div>
      )}
    </section>
  );
}
