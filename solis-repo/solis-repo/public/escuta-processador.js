// Processador de áudio da escuta da palavra "Solis" (src/escuta.ts): pega o
// microfone já em 16 kHz (o AudioContext reamostra) e manda pro lado de fora
// em quadros de 512 amostras PCM de 16 bits — o tamanho do quadro do Porcupine
// e o formato do WebSocket /escuta. Roda na thread de áudio, não na da tela.
class EscutaProcessador extends AudioWorkletProcessor {
  constructor() {
    super();
    this.quadro = new Int16Array(512);
    this.n = 0;
  }

  process(entradas) {
    const canal = entradas[0] && entradas[0][0];
    if (!canal) return true;
    for (let i = 0; i < canal.length; i++) {
      const v = Math.max(-1, Math.min(1, canal[i]));
      this.quadro[this.n++] = v < 0 ? v * 0x8000 : v * 0x7fff;
      if (this.n === this.quadro.length) {
        this.port.postMessage(this.quadro.buffer, [this.quadro.buffer]);
        this.quadro = new Int16Array(512);
        this.n = 0;
      }
    }
    return true;
  }
}

registerProcessor('escuta-processador', EscutaProcessador);
