import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { Botao } from '../components/Controles';
import {
  abrirNavegador,
  escolherNavegador,
  guardarChaveNavegador,
  lerNavegador,
  type Navegador,
} from '../servidor';

/** Configurações → Navegador: em qual navegador o Claude abre, lê e preenche
 *  páginas, como o Claude in Chrome (backend/solis/navegador.py). Uma janela
 *  do Chrome ou do Edge do PC, com um perfil só do Solis: os logins feitos
 *  nela ficam guardados ali, longe do perfil de sempre.
 *
 *  Aprovado pelo Matheus em 15/11/2026 nos 3 temas e 2 navs — desenho próprio:
 *  o cartão e as linhas do de Cérebros (layout.configuracoes.cerebros), o
 *  seletor e o botão dos campos das Tarefas agendadas (--mac-*). Medida nova em
 *  layout.configuracoes.navegador.
 *
 *  Aprovado pelo Matheus em 18/11/2026 nos 3 temas e 2 navs: "Qual janela" (a do
 *  Solis ou o navegador de sempre dele, pela extensão do Playwright), a linha
 *  da extensão e a da chave. Nenhuma medida nova: as linhas, o seletor e o
 *  campo de colar a chave são os mesmos deste cartão e do de Cérebros. */

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
  const sempre = !!nav?.sempre && valor !== 'desligado';

  const guardarChave = async (chave: string) => {
    definirErro('');
    const r = await guardarChaveNavegador(chave);
    if (r) definirNav(r);
    else definirErro('Não consegui guardar agora: o servidor do Solis não respondeu.');
    return !!r;
  };

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
        O Claude abre, lê e preenche páginas numa janela do navegador que você vê: uma só do Solis, ou o seu
        navegador de sempre. Abrir e ler é livre; clicar, escrever e preencher pedem você antes.
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
                  : sempre
                    ? !nav.extensao
                      ? `${nome}. Falta a extensão: o Claude está sem navegador.`
                      : nav.aberto
                        ? `${nome}. Ligado ao seu agora.`
                        : `${nome}. Liga ao seu quando o Claude precisar.`
                    : nav.aberto
                      ? `${nome}. A janela está aberta agora.`
                      : `${nome}. A janela abre quando o Claude precisar.`}
              </div>
            </div>
            <select
              value={valor}
              // Trocar de Chrome pra Edge mantém a janela escolhida (a do Solis ou a de sempre).
              onChange={(e) =>
                void escolher(e.target.value !== 'desligado' && sempre ? `${e.target.value}:sempre` : e.target.value)
              }
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
                <div className="text-text-primary" style={{ fontSize: 'var(--cfg-rotulo)' }}>Qual janela</div>
                <div className="text-text-secondary" style={{ ...dica, textWrap: 'pretty' }}>
                  {sempre
                    ? 'O seu de sempre, com as suas abas e contas, pela extensão do Playwright. O Claude só mexe nas abas que você der a ele ou que ele abrir, e abrir um site novo pede você.'
                    : 'Uma janela só do Solis, com os logins separados dos seus.'}
                </div>
              </div>
              <select
                value={sempre ? 'sempre' : 'solis'}
                onChange={(e) => void escolher(e.target.value === 'sempre' ? `${valor}:sempre` : valor)}
                aria-label="Qual janela"
                className={`solis-data text-text-secondary bg-canvas shrink-0 ${CAMPO}`}
                style={caixa}
              >
                <option value="solis">Janela do Solis</option>
                <option value="sempre">O seu de sempre</option>
              </select>
            </div>
          )}

          {sempre && !nav.extensao && (
            <div
              className="flex items-center justify-between border-t border-divider"
              style={{ ...linha, gap: 'var(--cer-controles-gap)' }}
            >
              <div className="min-w-0">
                <div className="text-text-primary" style={{ fontSize: 'var(--cfg-rotulo)' }}>A extensão</div>
                <div className="text-text-secondary" style={{ ...dica, textWrap: 'pretty' }}>
                  Falta a extensão do Playwright (da Microsoft) no seu {nome}. Instale pela loja, no perfil que você
                  usa; enquanto isso, o Claude fica sem navegador.
                </div>
              </div>
              <a
                href={nav.extensao_url}
                target="_blank"
                rel="noreferrer"
                className="text-accent hover:underline shrink-0"
                style={{ fontSize: 'var(--mac-botao-texto)' }}
              >
                Abrir a loja
              </a>
            </div>
          )}

          {sempre && nav.extensao && <LinhaChave nav={nav} guardar={guardarChave} />}

          {sempre && nav.extensao && (
            <div
              className="flex items-center justify-between border-t border-divider"
              style={{ ...linha, gap: 'var(--cer-controles-gap)' }}
            >
              <div className="min-w-0">
                <div className="text-text-primary" style={{ fontSize: 'var(--cfg-rotulo)' }}>Ligar agora</div>
                <div className="text-text-secondary" style={{ ...dica, textWrap: 'pretty' }}>
                  Liga o Solis ao seu {nome} e abre uma aba no grupo dele, pra conferir.
                </div>
              </div>
              <Botao onClick={() => void abrir()} disabled={abrindo}>
                {abrindo ? 'Ligando…' : 'Ligar'}
              </Botao>
            </div>
          )}

          {valor !== 'desligado' && !sempre && (
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

/** "Ligar sem perguntar": a chave da extensão (está na página dela, ao clicar
 *  no ícone). O campo de colar abre na própria linha, como o de Cérebros. */
function LinhaChave({ nav, guardar }: { nav: Navegador; guardar: (chave: string) => Promise<boolean> }) {
  const [colando, definirColando] = useState(false);
  const [chave, definirChave] = useState('');
  const [salvando, definirSalvando] = useState(false);
  const campo = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (colando) campo.current?.focus();
  }, [colando]);

  const salvar = async (valor: string) => {
    definirSalvando(true);
    const ok = await guardar(valor);
    definirSalvando(false);
    if (ok) {
      definirColando(false);
      definirChave('');
    }
  };

  const dica = { fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)', maxWidth: 'var(--cer-texto-max)' } as const;
  return (
    <div className="border-t border-divider" style={{ marginTop: 'var(--cer-linha-pad)', paddingTop: 'var(--cer-linha-pad)' }}>
      <div className="flex items-center justify-between" style={{ gap: 'var(--cer-controles-gap)' }}>
        <div className="min-w-0">
          <div className="text-text-primary" style={{ fontSize: 'var(--cfg-rotulo)' }}>Ligar sem perguntar</div>
          <div className="text-text-secondary" style={{ ...dica, textWrap: 'pretty' }}>
            {nav.chave
              ? 'A chave da extensão está guardada: o Solis liga sozinho, numa aba nova.'
              : 'Sem a chave, cada vez que o Solis liga, o seu navegador mostra a página da extensão pra você aprovar e escolher as abas. A chave fica na página da extensão (clique no ícone dela).'}
          </div>
        </div>
        {!colando &&
          (nav.chave ? (
            <Botao onClick={() => void salvar('')} disabled={salvando}>
              Apagar a chave
            </Botao>
          ) : (
            <Botao onClick={() => definirColando(true)}>Colar a chave</Botao>
          ))}
      </div>
      {colando && (
        <div style={{ marginTop: 'var(--mac-botao-top)', maxWidth: 'var(--cer-texto-max)' }}>
          <input
            ref={campo}
            type="password"
            value={chave}
            autoComplete="off"
            spellCheck={false}
            onChange={(e) => definirChave(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && chave.trim()) void salvar(chave);
              else if (e.key === 'Escape') definirColando(false);
            }}
            placeholder="Cole a chave da extensão"
            aria-label="Chave da extensão"
            className="block w-full bg-transparent outline-none text-text-primary placeholder:text-text-secondary border border-divider focus:border-[color-mix(in_srgb,var(--accent)_55%,transparent)]"
            style={{
              fontSize: 'var(--cfg-dica)',
              borderRadius: 'var(--mac-campo-raio)',
              padding: 'var(--mac-campo-py) var(--mac-campo-px)',
            }}
          />
          <div className="flex items-center flex-wrap" style={{ gap: 'var(--mac-botao-gap)', marginTop: 'var(--mac-botao-top)' }}>
            <Botao tipo="destaque" onClick={() => void salvar(chave)} disabled={salvando || !chave.trim()}>
              {salvando ? 'Guardando…' : 'Salvar'}
            </Botao>
            <Botao onClick={() => definirColando(false)}>Cancelar</Botao>
          </div>
        </div>
      )}
    </div>
  );
}
