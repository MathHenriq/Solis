import { useEffect, useState, type CSSProperties } from 'react';
import { Botao } from '../components/Controles';
import { abrirNavegador, escolherNavegador, lerNavegador, type Navegador } from '../servidor';

/** Configurações → Navegador: em qual navegador o Claude abre, lê e preenche
 *  páginas, como o Claude in Chrome (backend/solis/navegador.py). Uma janela
 *  do Chrome ou do Edge do PC, com um perfil só do Solis: os logins feitos
 *  nela ficam guardados ali, longe do perfil de sempre.
 *
 *  Aprovado pelo Matheus em 15/11/2026 nos 3 temas e 2 navs — desenho próprio:
 *  o cartão e as linhas do de Cérebros (layout.configuracoes.cerebros), o
 *  seletor e o botão dos campos das Tarefas agendadas (--mac-*). Medida nova em
 *  layout.configuracoes.navegador. */

const CAMPO =
  'bg-transparent outline-none text-text-primary border border-divider focus:border-[color-mix(in_srgb,var(--accent)_55%,transparent)]';

export function CartaoNavegador() {
  // undefined = lendo; null = servidor fora.
  const [nav, definirNav] = useState<Navegador | null | undefined>(undefined);
  const [abrindo, definirAbrindo] = useState(false);
  const [erro, definirErro] = useState('');

  useEffect(() => {
    void lerNavegador().then(definirNav);
    // A janela pode abrir e fechar pelo Claude, numa conversa: "aberto agora" acompanha.
    const t = window.setInterval(() => void lerNavegador().then((n) => n && definirNav(n)), 15000);
    return () => window.clearInterval(t);
  }, []);

  const escolher = async (valor: string) => {
    definirErro('');
    const r = await escolherNavegador(valor);
    if (r) definirNav(r);
    else definirErro('Não consegui trocar agora: o servidor do Solis não respondeu.');
  };

  const abrir = async () => {
    definirAbrindo(true);
    definirErro('');
    const r = await abrirNavegador();
    definirAbrindo(false);
    if ('erro' in r) definirErro(r.erro);
    else definirNav(r);
  };

  const dica = { fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)', maxWidth: 'var(--cer-texto-max)' } as const;
  const linha = { marginTop: 'var(--cer-linha-pad)', paddingTop: 'var(--cer-linha-pad)' } as const;
  const caixa: CSSProperties = {
    height: 'var(--mac-botao-h)',
    borderRadius: 'var(--mac-campo-raio)',
    padding: '0 var(--mac-campo-px)',
    fontSize: 'var(--mac-botao-texto)',
    width: 'var(--nav-escolha-l)',
  };
  const nome = nav?.instalados.find((i) => i.canal === nav.escolhido)?.nome;
  const valor = nav ? (nav.desligado || !nav.escolhido ? 'desligado' : nav.escolhido) : 'desligado';

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
      <h2 className="text-text-primary" style={{ fontSize: 'var(--cfg-secao)' }}>Navegador</h2>
      <p className="text-text-secondary" style={{ ...dica, textWrap: 'pretty' }}>
        O Claude abre, lê e preenche páginas numa janela do navegador que você vê, com um perfil só do Solis,
        separado do seu de sempre. Abrir e ler é livre; clicar, escrever e preencher pedem você antes.
      </p>

      {nav === undefined && <p className="text-text-secondary" style={{ ...dica, ...linha }}>Vendo…</p>}
      {nav === null && (
        <p className="text-text-secondary" style={{ ...dica, ...linha }}>
          Servidor do Solis desligado. Iniciar com npm run backend.
        </p>
      )}
      {nav && !nav.instalados.length && (
        <p className="text-text-secondary border-t border-divider" style={{ ...dica, ...linha }}>
          Nenhum navegador que o Claude consiga usar neste PC: instale o Google Chrome ou o Microsoft Edge.
        </p>
      )}
      {nav && nav.instalados.length > 0 && !nav.pronto && (
        <p className="text-[var(--erro)] border-t border-divider" style={{ ...dica, ...linha }}>
          Falta o servidor do navegador: rode npm install na pasta do Solis.
        </p>
      )}

      {nav && nav.instalados.length > 0 && nav.pronto && (
        <>
          <div
            className="flex items-center justify-between border-t border-divider"
            style={{ ...linha, gap: 'var(--cer-controles-gap)' }}
          >
            <div className="min-w-0">
              <div className="text-text-primary" style={{ fontSize: 'var(--cfg-rotulo)' }}>Qual navegador</div>
              <div className="text-text-secondary" style={dica}>
                {valor === 'desligado'
                  ? 'Desligado: o Claude só lê páginas, sem abrir janela.'
                  : nav.aberto
                    ? `${nome}. A janela está aberta agora.`
                    : `${nome}. A janela abre quando o Claude precisar.`}
              </div>
            </div>
            <select
              value={valor}
              onChange={(e) => void escolher(e.target.value)}
              aria-label="Qual navegador"
              className={`solis-data text-text-secondary bg-canvas shrink-0 ${CAMPO}`}
              style={caixa}
            >
              {nav.instalados.map((i) => (
                <option key={i.canal} value={i.canal}>{i.nome}</option>
              ))}
              <option value="desligado">Desligado</option>
            </select>
          </div>

          {valor !== 'desligado' && (
            <div
              className="flex items-center justify-between border-t border-divider"
              style={{ ...linha, gap: 'var(--cer-controles-gap)' }}
            >
              <div className="min-w-0">
                <div className="text-text-primary" style={{ fontSize: 'var(--cfg-rotulo)' }}>Suas contas</div>
                <div className="text-text-secondary" style={{ ...dica, textWrap: 'pretty' }}>
                  Entre pela janela do Solis nos sites que o Claude vai usar: o login fica guardado nela. Senha
                  você digita; o Claude nunca.
                </div>
              </div>
              <Botao onClick={() => void abrir()} disabled={abrindo}>
                {abrindo ? 'Abrindo…' : 'Abrir o navegador'}
              </Botao>
            </div>
          )}
        </>
      )}

      {erro && (
        <div className="text-[var(--erro)]" style={{ fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)' }}>
          {erro}
        </div>
      )}
    </section>
  );
}
