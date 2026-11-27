import { useEffect, useState } from 'react';
import { Interruptor } from '../components/Controles';
import {
  abertoPeloServidor,
  guardarServidorDoPC,
  juntarComServidor,
  lerServidorDoPC,
  type ContagemJuntar,
  type ServidorDoPC,
} from '../servidor';

/** Configurações → Servidor (backend/solis/juntar.py, 26/11/2026): o cérebro na
 *  nuvem com que o Solis do PC se junta. Leva daqui as conversas, as memórias, as
 *  tarefas e a agenda, e traz de lá o que foi dito e aprendido pelo celular — sem
 *  o privado, que fica só onde nasceu. Rodar de novo não duplica nada.
 *
 *  Só no PC: aberto pelo servidor (o celular), o cartão não aparece.
 *  PROVISÓRIO: desenho próprio no molde dos outros cartões; o visual é refeito no fim. */

function resumo(c: ContagemJuntar): string {
  const partes = [
    [c.conversas, 'conversa', 'conversas'],
    [c.mensagens, 'mensagem', 'mensagens'],
    [c.memorias, 'memória', 'memórias'],
    [c.tarefas, 'tarefa', 'tarefas'],
    [c.compromissos, 'compromisso', 'compromissos'],
    [c.feitas, 'tarefa feita', 'tarefas feitas'],
  ]
    .filter(([n]) => (n as number) > 0)
    .map(([n, um, varios]) => `${n} ${n === 1 ? um : varios}`);
  return partes.length ? partes.join(', ') : 'nada novo';
}

export function CartaoServidor() {
  const [estado, definirEstado] = useState<ServidorDoPC | null | undefined>(undefined);
  const [endereco, definirEndereco] = useState('');
  const [senha, definirSenha] = useState('');
  const [ocupado, definirOcupado] = useState(false);
  const [recado, definirRecado] = useState<{ texto: string; erro?: boolean } | null>(null);

  useEffect(() => {
    void lerServidorDoPC().then((s) => {
      definirEstado(s);
      if (s) definirEndereco(s.endereco);
    });
  }, []);

  if (abertoPeloServidor) return null;

  const trocarUsaPc = async (usa: boolean) => {
    definirRecado(null);
    const s = await guardarServidorDoPC(estado?.endereco ?? endereco, '', usa);
    if (!s) return definirRecado({ texto: 'O Solis do PC não respondeu.', erro: true });
    definirEstado(s);
  };

  const guardar = async () => {
    definirRecado(null);
    const s = await guardarServidorDoPC(endereco, senha);
    if (!s) return definirRecado({ texto: 'O Solis do PC não respondeu.', erro: true });
    definirEstado(s);
    definirEndereco(s.endereco);
    definirSenha('');
    definirRecado({ texto: 'Guardado.' });
  };

  const juntar = async () => {
    definirOcupado(true);
    definirRecado(null);
    const r = await juntarComServidor();
    definirOcupado(false);
    if (!r.ok) return definirRecado({ texto: r.motivo, erro: true });
    definirRecado({ texto: `Trazido do servidor: ${resumo(r.trazidos)}. Levado pra ele: ${resumo(r.levados)}.` });
    definirEstado(await lerServidorDoPC());
  };

  const dica = { fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)', maxWidth: 'var(--cer-texto-max)' } as const;
  const linha = { marginTop: 'var(--cer-linha-pad)', paddingTop: 'var(--cer-linha-pad)' } as const;
  const campo = {
    fontSize: 'var(--cfg-dica)',
    padding: '8px 12px',
    borderRadius: 10,
    background: 'transparent',
    minWidth: 0,
  } as const;
  const botao = { padding: '8px 14px', borderRadius: 10, fontSize: 'var(--cfg-dica)' } as const;

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
      <h2 className="text-text-primary" style={{ fontSize: 'var(--cfg-secao)' }}>Servidor</h2>
      <p className="text-text-secondary" style={{ ...dica, textWrap: 'pretty' }}>
        O Solis na nuvem, que responde pelo celular com o PC desligado. Juntar leva daqui as conversas, as memórias, as
        tarefas e a agenda, e traz de lá o que você disse pelo celular. O privado não viaja: fica só onde nasceu.
      </p>

      {estado === undefined && <p className="text-text-secondary" style={{ ...dica, ...linha }}>Vendo…</p>}
      {estado === null && (
        <p className="text-text-secondary" style={{ ...dica, ...linha }}>Servidor do Solis desligado. Iniciar com npm run backend.</p>
      )}
      {estado && (
        <div className="border-t border-divider" style={{ ...linha, display: 'grid', gap: 10 }}>
          <input
            className="border border-divider text-text-primary"
            style={campo}
            value={endereco}
            onChange={(e) => definirEndereco(e.target.value)}
            placeholder="Endereço do servidor (ex.: solis.seu-tailnet.ts.net)"
            aria-label="Endereço do servidor"
          />
          <input
            className="border border-divider text-text-primary"
            style={campo}
            type="password"
            value={senha}
            onChange={(e) => definirSenha(e.target.value)}
            placeholder={estado.tem_senha ? 'Senha guardada (deixe vazio pra manter)' : 'Senha do servidor (o token)'}
            aria-label="Senha do servidor"
            autoComplete="off"
          />
          <div className="flex items-center" style={{ gap: 10, flexWrap: 'wrap' }}>
            <button type="button" onClick={() => void guardar()} className="border border-divider text-text-primary hover:bg-[var(--mem-hover)]" style={botao}>
              Guardar
            </button>
            <button
              type="button"
              onClick={() => void juntar()}
              disabled={ocupado || !estado.endereco || !estado.tem_senha}
              className="border border-divider text-text-primary hover:bg-[var(--mem-hover)] disabled:opacity-50"
              style={botao}
            >
              {ocupado ? 'Juntando…' : 'Juntar agora'}
            </button>
          </div>
          <div className="flex items-center justify-between border-t border-divider" style={{ ...linha, gap: 'var(--cer-controles-gap)' }}>
            <div className="min-w-0">
              <div className="text-text-primary" style={{ fontSize: 'var(--cfg-rotulo)' }}>Deixar o servidor usar este PC</div>
              <div className="text-text-secondary" style={{ ...dica, textWrap: 'pretty' }}>
                Com o PC ligado, o Solis do celular usa o terminal, as pastas liberadas e a tela daqui (ler, clicar e digitar).
                Cada comando e cada ação na tela pedem você antes, no celular, com o print do lugar.
                {estado.usa_pc && (estado.pc_ligado ? ' Ligado no servidor agora.' : estado.pc_erro ? ` Sem o servidor: ${estado.pc_erro}.` : ' Ligando…')}
              </div>
            </div>
            <Interruptor ligado={estado.usa_pc} rotulo="Deixar o servidor usar este PC" aoTrocar={(v) => void trocarUsaPc(v)} />
          </div>
          {estado.ultima && !recado && (
            <p className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)' }}>
              Última vez em {new Date(estado.ultima.quando).toLocaleString('pt-BR')}: trazido {resumo(estado.ultima.trazidos)};
              levado {resumo(estado.ultima.levados)}.
            </p>
          )}
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
