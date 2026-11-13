import { useEffect, useState } from 'react';
import { Botao } from '../components/Controles';
import { lerDocumentos, prepararDocumentos, type EstadoDocumentos } from '../servidor';

/** Configurações → Documentos: o Claude cria Word, Excel, PowerPoint e PDF de
 *  verdade pelas skills da conta do claude.ai; as bibliotecas que elas usam
 *  ficam numa pasta só do Solis (backend/solis/documentos.py).
 *
 *  PROVISÓRIO — desenho próprio (13/11/2026): o cartão e as linhas do de
 *  Cérebros (layout.configuracoes.cerebros), com o botão da edição da Memória
 *  (layout.configuracoes.cerebros._documentos). Precisa do aval do Matheus. */

export function CartaoDocumentos() {
  // undefined = lendo; null = servidor fora.
  const [estado, definirEstado] = useState<EstadoDocumentos | null | undefined>(undefined);
  const [preparando, definirPreparando] = useState(false);
  const [erro, definirErro] = useState<string | null>(null);

  useEffect(() => {
    void lerDocumentos().then(definirEstado);
  }, []);

  const preparar = async () => {
    definirPreparando(true);
    definirErro(null);
    const r = await prepararDocumentos();
    definirPreparando(false);
    if ('erro' in r) definirErro(r.erro);
    else definirEstado(r);
  };

  const dica = { fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)', maxWidth: 'var(--cer-texto-max)' } as const;

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
      <h2 className="text-text-primary" style={{ fontSize: 'var(--cfg-secao)' }}>Documentos</h2>
      <p className="text-text-secondary" style={{ ...dica, textWrap: 'pretty' }}>
        O Claude cria Word, Excel, PowerPoint e PDF de verdade, com as skills da sua conta do claude.ai. O arquivo
        aparece embaixo da resposta, pra abrir.
      </p>

      <div
        className="flex items-center justify-between border-t border-divider"
        style={{ marginTop: 'var(--cer-linha-pad)', paddingTop: 'var(--cer-linha-pad)', gap: 'var(--cer-controles-gap)' }}
      >
        <div className="min-w-0">
          <div className="text-text-primary" style={{ fontSize: 'var(--cfg-rotulo)' }}>
            Bibliotecas dos documentos
          </div>
          <div className="text-text-secondary" style={dica}>
            {estado === undefined && 'Vendo…'}
            {estado === null && 'Servidor do Solis desligado. Iniciar com npm run backend.'}
            {estado?.pronto && 'Prontas, numa pasta só do Solis (cerca de 105 MB).'}
            {estado && !estado.pronto && !preparando &&
              `Faltam: ${estado.falta.join(', ')}. Preparar baixa cerca de 105 MB do npm e do PyPI, numa pasta só do Solis.`}
            {preparando && 'Baixando e instalando… leva um ou dois minutos.'}
          </div>
          {erro && (
            <div className="text-[var(--erro)]" style={dica}>
              Não deu: {erro}
            </div>
          )}
        </div>
        {estado && (
          <div className="shrink-0">
            <Botao tipo={estado.pronto ? 'texto' : 'destaque'} onClick={preparar} disabled={preparando}>
              {preparando ? 'Preparando…' : estado.pronto ? 'Preparar de novo' : 'Preparar'}
            </Botao>
          </div>
        )}
      </div>
    </section>
  );
}
