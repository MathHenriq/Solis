import { useEffect, useRef, useState } from 'react';
import { Botao } from '../components/Controles';
import { definirEscutaLigada, escutaLigada } from '../escuta';
import {
  enviarTesteEscuta,
  lerRoteiroTeste,
  listarTestesEscuta,
  type MedidaEscuta,
  type RoteiroTeste,
} from '../servidor';

/** Configurações → Voz → Teste da escuta (backend/solis/voz_teste.py): o
 *  Matheus fala um roteiro de uns 3 minutos e meio e o Solis mede a escuta com
 *  a voz e o microfone dele — quantas chamadas acordaram, quantas viraram o
 *  pedido certo, quanto tempo levou e quantos alarmes falsos (docs/IDEIAS.md:
 *  "só existe o que funciona", meta 9 em 10).
 *
 *  A gravação usa a mesma captura da escuta (public/escuta-processador.js,
 *  16 kHz), e a frase na tela é guiada pelo tempo da própria gravação: o
 *  roteiro guardado bate com o áudio, sem o atraso do relógio da tela. A escuta
 *  de verdade fica pausada enquanto grava (senão "Solis, que horas são" do
 *  roteiro viraria mensagem) e volta como estava.
 *
 *  PROVISÓRIO — desenho próprio (16/11/2026), precisa da aprovação do Matheus:
 *  uma linha do cartão Voz com o botão; gravando, a frase grande (--cfg-secao),
 *  a barra do cartão Uso (--uso-barra-*) e o Parar; no fim, os números em linhas
 *  como as do cartão Uso. Ver layout.configuracoes.testeEscuta. */

type Fase = 'parado' | 'gravando' | 'enviando' | 'medindo' | 'pronto' | 'erro';

function wavDe(pedacos: Int16Array[], total: number): Blob {
  const dados = new DataView(new ArrayBuffer(44 + total * 2));
  const texto = (o: number, s: string) => [...s].forEach((c, i) => dados.setUint8(o + i, c.charCodeAt(0)));
  texto(0, 'RIFF');
  dados.setUint32(4, 36 + total * 2, true);
  texto(8, 'WAVE');
  texto(12, 'fmt ');
  dados.setUint32(16, 16, true);
  dados.setUint16(20, 1, true);
  dados.setUint16(22, 1, true);
  dados.setUint32(24, 16000, true);
  dados.setUint32(28, 32000, true);
  dados.setUint16(32, 2, true);
  dados.setUint16(34, 16, true);
  texto(36, 'data');
  dados.setUint32(40, total * 2, true);
  let o = 44;
  for (const p of pedacos) {
    for (let i = 0; i < p.length; i++, o += 2) dados.setInt16(o, p[i], true);
  }
  return new Blob([dados.buffer], { type: 'audio/wav' });
}

const segundos = (s: number | null) => (s === null ? '—' : `${s.toFixed(1).replace('.', ',')} s`);

export function TesteEscuta() {
  const [roteiro, definirRoteiro] = useState<RoteiroTeste | null>(null);
  const [fase, definirFase] = useState<Fase>('parado');
  const [agora, definirAgora] = useState(0);
  const [erro, definirErro] = useState('');
  const [medida, definirMedida] = useState<MedidaEscuta | null>(null);
  // A mesma gravação medida com o Silero VAD no lugar da energia (em teste).
  const [silero, definirSilero] = useState<MedidaEscuta | null>(null);
  const parar = useRef<(() => void) | null>(null);

  useEffect(() => {
    void lerRoteiroTeste().then(definirRoteiro);
    // O último teste medido, se houver.
    void listarTestesEscuta().then((l) => {
      const ultimo = l?.testes.find((t) => t.medidas.atual);
      if (ultimo) {
        definirMedida(ultimo.medidas.atual);
        definirSilero(ultimo.medidas.silero ?? null);
        definirFase('pronto');
      }
    });
    return () => parar.current?.();
  }, []);

  async function comecar() {
    if (!roteiro) return;
    definirErro('');
    const estavaLigada = escutaLigada();
    if (estavaLigada) definirEscutaLigada(false);
    const restaurar = () => estavaLigada && definirEscutaLigada(true);
    let fluxo: MediaStream;
    try {
      fluxo = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
      });
    } catch {
      restaurar();
      definirErro('Sem acesso ao microfone. Libere no navegador.');
      definirFase('erro');
      return;
    }
    const contexto = new AudioContext({ sampleRate: 16000 });
    await contexto.audioWorklet.addModule('/escuta-processador.js');
    const no = new AudioWorkletNode(contexto, 'escuta-processador');
    const pedacos: Int16Array[] = [];
    let total = 0;
    let acabou = false;
    const fechar = () => {
      acabou = true;
      fluxo.getTracks().forEach((t) => t.stop());
      void contexto.close();
      restaurar();
    };
    parar.current = () => {
      if (acabou) return;
      fechar();
      definirFase('parado');
      definirAgora(0);
    };
    no.port.onmessage = async (e) => {
      if (acabou) return;
      const q = new Int16Array(e.data as ArrayBuffer);
      pedacos.push(q);
      total += q.length;
      const t = total / 16000;
      definirAgora(t);
      if (t >= roteiro.duracao) {
        fechar();
        definirFase('enviando');
        const r = await enviarTesteEscuta(wavDe(pedacos, total), roteiro.passos);
        if ('erro' in r) {
          definirErro(r.erro);
          definirFase('erro');
          return;
        }
        definirFase('medindo');
        esperarMedida(r.id);
      }
    };
    contexto.createMediaStreamSource(fluxo).connect(no);
    definirAgora(0);
    definirFase('gravando');
  }

  function esperarMedida(id: string) {
    const conferir = async () => {
      const l = await listarTestesEscuta();
      const medidas = l?.testes.find((t) => t.id === id)?.medidas;
      if (medidas?.atual) {
        definirMedida(medidas.atual);
        definirSilero(medidas.silero ?? null);
        definirFase('pronto');
      }
      // Continua até a do Silero chegar também (vem depois: o Whisper é um só).
      if (!medidas?.silero) window.setTimeout(conferir, 3000);
    };
    window.setTimeout(conferir, 3000);
  }

  const passo = roteiro?.passos.find((p) => agora >= p.inicio - roteiro.preparo && agora < p.fim);
  const falando = passo && agora >= passo.inicio;
  const dica = { fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)', maxWidth: 'var(--cer-texto-max)', textWrap: 'pretty' } as const;
  const linhaNumero = (rotulo: string, valor: string, ruim = false) => (
    <div className="flex items-baseline justify-between border-t border-divider" style={{ paddingTop: 'var(--cfg-linha-pad)', paddingBottom: 'var(--cfg-linha-pad)', gap: 'var(--cer-controles-gap)' }}>
      <span className="text-text-primary" style={{ fontSize: 'var(--cfg-rotulo)' }}>{rotulo}</span>
      <span className={ruim ? 'text-[var(--erro)]' : 'text-text-secondary'} style={{ fontSize: 'var(--cfg-dica)' }}>{valor}</span>
    </div>
  );

  return (
    <div className="border-t border-divider" style={{ paddingTop: 'var(--cfg-linha-pad)', paddingBottom: 'var(--cfg-linha-pad)' }}>
      <div className="flex items-center justify-between" style={{ gap: 'var(--cer-controles-gap)' }}>
        <div className="min-w-0">
          <div className="text-text-primary" style={{ fontSize: 'var(--cfg-rotulo)' }}>Teste da escuta</div>
          <div className="text-text-secondary" style={dica}>
            {fase === 'gravando'
              ? 'Gravando. Fale o que aparecer, no seu tom de sempre. A escuta fica pausada até acabar.'
              : fase === 'enviando' || fase === 'medindo'
                ? 'Medindo a escuta na sua gravação… leva uns minutos (cada fala passa pelo Whisper).'
                : `Uns ${roteiro ? Math.round(roteiro.duracao / 60) : 4} minutos: a tela mostra o que falar e quando, e o Solis mede quantas vezes acordou e entendeu, em quanto tempo, e os alarmes falsos. A gravação fica só neste computador.`}
          </div>
        </div>
        {fase === 'gravando' ? (
          <Botao onClick={() => parar.current?.()}>Parar</Botao>
        ) : (
          <Botao tipo={fase === 'pronto' ? undefined : 'destaque'} onClick={() => void comecar()} disabled={!roteiro || fase === 'enviando' || fase === 'medindo'}>
            {fase === 'pronto' ? 'Testar de novo' : 'Testar'}
          </Botao>
        )}
      </div>

      {fase === 'gravando' && roteiro && (
        <div style={{ marginTop: 'var(--cer-linha-pad)' }}>
          <div
            aria-live="polite"
            className={falando ? 'text-text-primary' : 'text-text-secondary'}
            style={{ fontSize: 'var(--cfg-secao)', minHeight: 'var(--te-frase-h)', maxWidth: 'var(--cer-texto-max)', textWrap: 'pretty' }}
          >
            {agora < roteiro.inicio
              ? 'Silêncio por uns segundos: o Solis está ouvindo o ambiente.'
              : passo
                ? falando
                  ? passo.mostrar
                  : `Prepare-se: ${passo.mostrar}`
                : '…'}
          </div>
          <div
            role="progressbar"
            aria-valuenow={Math.round((agora / roteiro.duracao) * 100)}
            aria-valuemin={0}
            aria-valuemax={100}
            className="w-full overflow-hidden"
            style={{ height: 'var(--uso-barra-h)', borderRadius: 999, background: 'var(--divider)', marginTop: 'var(--uso-barra-top)' }}
          >
            <div style={{ height: '100%', width: `${Math.min(100, (agora / roteiro.duracao) * 100)}%`, borderRadius: 999, background: 'var(--accent)' }} />
          </div>
          <div className="text-text-secondary" style={dica}>
            {passo ? `${passo.i + 1} de ${roteiro.passos.length}` : ' '} · falta {Math.max(0, Math.ceil(roteiro.duracao - agora))} s
          </div>
        </div>
      )}

      {fase === 'pronto' && medida && (
        <div style={{ marginTop: 'var(--cfg-dica-top)' }}>
          <div className={medida.passou ? 'text-accent' : 'text-[var(--erro)]'} style={{ fontSize: 'var(--cfg-dica)', marginBottom: 'var(--cfg-dica-top)' }}>
            {medida.passou ? 'Passou na meta (9 em 10, sem alarme falso).' : 'Não passou na meta (9 em 10, sem alarme falso).'}
          </div>
          {linhaNumero('Acordou com "Solis"', `${medida.acordou} de ${medida.chamadas}`, medida.acordou / medida.chamadas < 0.9)}
          {linhaNumero('Entendeu o pedido', `${medida.entendeu} de ${medida.chamadas}`, medida.entendeu / medida.chamadas < 0.9)}
          {linhaNumero('Alarmes falsos', `${medida.falsos} em ${medida.trechos_sem} trechos sem "Solis"`, medida.falsos > 0)}
          {linhaNumero('Do fim da fala ao texto', `${segundos(medida.latencia_mediana)} no meio, ${segundos(medida.latencia_max)} no pior`)}
          {linhaNumero(
            'Com o detector de fala novo (em teste)',
            silero
              ? `entendeu ${silero.entendeu} de ${silero.chamadas}, ${silero.falsos} falsos, ${segundos(silero.latencia_mediana)}`
              : 'medindo…',
          )}
        </div>
      )}

      {erro && (
        <div className="text-[var(--erro)]" style={{ fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)' }}>
          {erro}
        </div>
      )}
    </div>
  );
}
