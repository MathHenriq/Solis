/** Um pedaço da fala tocando enquanto chega (src/fala.ts).
 *
 *  Por que não só `new Audio(url)`: medido em 11/11/2026, o servidor manda o
 *  primeiro byte da Fish em 0,66 s, mas o <audio> lendo direto da URL juntava
 *  áudio até ~2–3 s antes de tocar — o mesmo tempo do áudio inteiro. Aqui o
 *  áudio entra no <audio> pela Media Source, pedaço por pedaço, e toca assim
 *  que o primeiro entra.
 *
 *  O que não é mp3 aos pedaços (o Gemini manda wav inteiro; a Kokoro também)
 *  toca como antes: inteiro, por um blob.
 *
 *  Abrir já começa a baixar (e a guardar o que chega): o pedaço seguinte
 *  carrega enquanto o atual toca. */
// Prazos (16/11/2026): a fonte do áudio tem de abrir em 5 s, e o áudio não pode
// ficar 15 s sem avançar (o primeiro som da Fish sai em ~0,8 s; a voz local, em
// até ~6 s pra frase inteira).
const ABRIR_MAX_MS = 5000;
const PARADO_MAX_MS = 15000;

export class PedacoDeFala {
  private pedacos: Uint8Array[] = [];
  private acabou = false;
  private erro = false;
  private avisar: (() => void) | null = null;
  private corte = new AbortController();
  private tipo = '';
  private pronto: Promise<boolean>;
  readonly el = new Audio();

  constructor(url: string) {
    this.pronto = this.baixar(url);
  }

  private async baixar(url: string): Promise<boolean> {
    try {
      const r = await fetch(url, { signal: this.corte.signal });
      if (!r.ok || !r.body) return false;
      this.tipo = (r.headers.get('content-type') ?? '').split(';')[0].trim();
      const leitor = r.body.getReader();
      void (async () => {
        try {
          for (;;) {
            const { done, value } = await leitor.read();
            if (done) break;
            this.pedacos.push(value);
            this.avisar?.();
          }
        } catch {
          this.erro = true;
        }
        this.acabou = true;
        this.avisar?.();
      })();
      return true;
    } catch {
      return false;
    }
  }

  /** O próximo pedaço que chegou, ou null no fim. */
  private async proximo(): Promise<Uint8Array | null> {
    while (!this.pedacos.length && !this.acabou) await new Promise<void>((ok) => (this.avisar = ok));
    this.avisar = null;
    return this.pedacos.shift() ?? null;
  }

  cancelar() {
    this.corte.abort();
    this.el.pause();
    this.el.removeAttribute('src');
    this.el.load();
  }

  /** Toca até o fim. `aoComecar`: o primeiro som saiu. false se não deu. */
  async tocar(aoComecar: () => void): Promise<boolean> {
    if (!(await this.pronto)) return false;
    const aos =
      this.tipo === 'audio/mpeg' && typeof MediaSource !== 'undefined' && MediaSource.isTypeSupported('audio/mpeg');
    if (!aos) {
      const partes: Uint8Array[] = [];
      for (let p = await this.proximo(); p; p = await this.proximo()) partes.push(p);
      if (this.erro || !partes.length) return false;
      const url = URL.createObjectURL(new Blob(partes as BlobPart[], { type: this.tipo || 'audio/wav' }));
      this.el.src = url;
      const ok = await this.esperarTocar(aoComecar);
      URL.revokeObjectURL(url);
      return ok;
    }

    const fonte = new MediaSource();
    const url = URL.createObjectURL(fonte);
    this.el.src = url;
    // Sem prazo, uma fonte que não abre deixava a fala (e a escuta, pausada) presa.
    const abriu = await new Promise<boolean>((ok) => {
      fonte.addEventListener('sourceopen', () => ok(true), { once: true });
      window.setTimeout(() => ok(false), ABRIR_MAX_MS);
    });
    if (!abriu) {
      URL.revokeObjectURL(url);
      return false;
    }
    const buffer = fonte.addSourceBuffer('audio/mpeg');
    // mp3 não traz carimbo de tempo: em sequência, cada pedaço vem depois do outro.
    buffer.mode = 'sequence';
    const anexar = (p: Uint8Array) =>
      new Promise<void>((ok, falha) => {
        buffer.addEventListener('updateend', () => ok(), { once: true });
        buffer.addEventListener('error', () => falha(new Error('buffer')), { once: true });
        buffer.appendBuffer(p as BufferSource);
      });
    const tocando = this.esperarTocar(aoComecar);
    try {
      for (let p = await this.proximo(); p; p = await this.proximo()) await anexar(p);
      if (fonte.readyState === 'open') fonte.endOfStream();
    } catch {
      this.erro = true;
      if (fonte.readyState === 'open') fonte.endOfStream('decode');
    }
    const ok = await tocando;
    URL.revokeObjectURL(url);
    return ok && !this.erro;
  }

  /** Toca até o fim. Áudio que empaca (PARADO_MAX_MS sem avançar) conta como
   *  falha: sem isso, o "terminou" nunca vinha e a escuta ficava pausada. */
  private esperarTocar(aoComecar: () => void): Promise<boolean> {
    return new Promise<boolean>((fim) => {
      let ultimo = Date.now();
      const vigia = window.setInterval(() => {
        if (Date.now() - ultimo > PARADO_MAX_MS) acabar(false);
      }, 1000);
      const acabar = (ok: boolean) => {
        window.clearInterval(vigia);
        fim(ok);
      };
      this.el.ontimeupdate = () => (ultimo = Date.now());
      this.el.onplaying = () => {
        ultimo = Date.now();
        aoComecar();
      };
      this.el.onended = () => acabar(true);
      this.el.onerror = () => acabar(false);
      this.el.play().catch(() => acabar(false));
    });
  }
}
