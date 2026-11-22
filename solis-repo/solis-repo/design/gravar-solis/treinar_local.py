"""Treina o detector da palavra "Solis" AQUI, no PC, sem Colab e sem PyTorch
(o Controle de Aplicativo do Windows bloqueia o PyTorch neste PC).

O modelo de uma palavra no openWakeWord é só uma camada pequena por cima de
duas peças fixas (o melespectrograma e a "espinha" de 96 números a cada 80 ms),
que o Solis já roda pelo onnxruntime (backend/solis/palavra.py). Então:

1. Marca onde a palavra "Solis" termina em cada gravação positiva (o Whisper
   turbo daqui, com o tempo de cada palavra): parte das gravações é "Solis, que
   horas são?" ou "Ei Solis", e o fim da palavra não é o fim do áudio.
2. Aumenta os dados: volume, barulho (fala de fundo dos negativos, ruído),
   eco de sala sintético, e silêncio/fundo antes.
3. Tira os vetores (16 × 96) com as mesmas peças do Solis. Positivo: as janelas
   que terminam logo depois da palavra. Negativo: tudo dos negativos, e o
   pedaço antes da palavra nos positivos.
4. Treina em numpy (MLP: 1536 → 64 → 1, Adam) e salva em .npz (palavra.py lê).
5. Mede nas 32 gravações guardadas (teste-local.txt), limpas e com barulho de
   fala por cima, e conta os alarmes falsos nos negativos guardados.

Uso: backend\\.venv\\Scripts\\python design\\gravar-solis\\treinar_local.py
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
import time
import unicodedata
import wave
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
REPO = AQUI.parents[1]
sys.path.insert(0, str(REPO / 'backend'))
from solis import palavra  # noqa: E402

TREINO = REPO / 'design' / '_treino-solis'
AMOSTRAS = Path(os.environ['LOCALAPPDATA']) / 'Solis' / 'voz' / 'amostras-solis'
SAIDA = palavra.PASTA / 'solis.npz'
TEMPOS = TREINO / 'tempos.json'
SR = 16000
rng = np.random.default_rng(7)


# — áudio ——————————————————————————————————————————————————————————————————————
def ler(caminho) -> np.ndarray:
    with wave.open(str(caminho)) as w:
        assert w.getframerate() == SR and w.getnchannels() == 1 and w.getsampwidth() == 2, caminho
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768


def rms(x):
    return float(np.sqrt(np.mean(x ** 2) + 1e-12))


def com_snr(sinal, fundo, snr_db):
    if len(fundo) < len(sinal):
        fundo = np.tile(fundo, int(np.ceil(len(sinal) / max(len(fundo), 1))) + 1)
    ini = rng.integers(0, len(fundo) - len(sinal) + 1)
    fundo = fundo[ini:ini + len(sinal)]
    alvo = rms(sinal) / (10 ** (snr_db / 20))
    return sinal + fundo * (alvo / max(rms(fundo), 1e-6))


def eco(x):
    """Sala sintética: resposta ao impulso de ruído com decaimento exponencial."""
    rt60 = rng.uniform(0.15, 0.6)
    n = int(SR * rt60)
    t = np.arange(n) / SR
    ir = rng.standard_normal(n) * np.exp(-6.9 * t / rt60)
    ir[0] = 1.0
    ir /= np.sqrt(np.sum(ir ** 2))
    m = len(x) + n - 1
    y = np.fft.irfft(np.fft.rfft(x, m) * np.fft.rfft(ir, m), m)[:len(x)]
    return y * (rms(x) / max(rms(y), 1e-6))


# — onde a palavra está (Whisper turbo daqui) ——————————————————————————————————
def _simples(t):
    return unicodedata.normalize('NFKD', t).encode('ascii', 'ignore').decode().lower()


def marcar_tempos(arquivos: list[str]) -> dict[str, list[float] | None]:
    tempos = json.loads(TEMPOS.read_text(encoding='utf-8')) if TEMPOS.exists() else {}
    falta = [a for a in arquivos if a not in tempos]
    if falta:
        from faster_whisper import WhisperModel

        from solis import voz
        # A biblioteca da placa (cublas) que vem com o Ollama, como o Solis faz (voz.py).
        if voz.CUBLAS_DO_OLLAMA.exists():
            os.environ['PATH'] = str(voz.CUBLAS_DO_OLLAMA) + os.pathsep + os.environ['PATH']
        modelo = WhisperModel('deepdml/faster-whisper-large-v3-turbo-ct2', device='cuda', compute_type='float16')
        for i, a in enumerate(falta):
            # O áudio já em 16 kHz (o decodificador do faster-whisper não abre com o av daqui).
            segs, _ = modelo.transcribe(ler(a), language='pt', word_timestamps=True, beam_size=5,
                                        initial_prompt='Solis.', vad_filter=False)
            achou = None
            for s in segs:
                for w in s.words or []:
                    if re.search(r'sol[iy]s|solis|soli$|solys|solace|solice|sole?s', _simples(w.word)):
                        achou = [round(w.start, 3), round(w.end, 3)]
                        break
                if achou:
                    break
            tempos[a] = achou
            if i % 50 == 0:
                print(f'  tempos {i}/{len(falta)}', flush=True)
        TEMPOS.write_text(json.dumps(tempos, indent=0), encoding='utf-8')
    return {a: tempos.get(a) for a in arquivos}


def fim_por_energia(x) -> tuple[float, float]:
    q = 160
    e = np.array([rms(x[i:i + q]) for i in range(0, len(x) - q, q)])
    voz = np.where(e > max(e.max() * 0.08, 1e-4))[0]
    return (voz[0] * q / SR, (voz[-1] + 1) * q / SR) if len(voz) else (0.0, len(x) / SR)


# — vetores (as peças do Solis) ————————————————————————————————————————————————
class Extrator:
    def __init__(self):
        self.mels = palavra._sessao(palavra.PASTA / palavra.MELS)
        self.espinha = palavra._sessao(palavra.PASTA / palavra.ESPINHA)
        self.e_mels = self.mels.get_inputs()[0].name
        self.e_esp = self.espinha.get_inputs()[0].name

    def vetores(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(vetores (m, 96), o instante em que cada um termina, em s)."""
        pcm = np.clip(x * 32768, -32768, 32767).astype(np.float32)[None, :]
        mel = np.squeeze(self.mels.run(None, {self.e_mels: pcm})[0]) / 10 + 2
        inicios = list(range(0, mel.shape[0] - palavra.JANELA_MEL + 1, palavra.PASSO_MEL))
        if not inicios:
            return np.zeros((0, 96), np.float32), np.zeros(0)
        lote = np.stack([mel[i:i + palavra.JANELA_MEL] for i in inicios])[:, :, :, None].astype(np.float32)
        saidas = []
        for k in range(0, len(lote), 64):
            try:
                saidas.append(np.squeeze(self.espinha.run(None, {self.e_esp: lote[k:k + 64]})[0]).reshape(-1, 96))
            except Exception:  # noqa: BLE001 — a espinha sem lote: uma por vez
                saidas.extend(np.squeeze(self.espinha.run(None, {self.e_esp: j[None]})[0]).reshape(-1, 96)
                              for j in lote[k:k + 64])
        vet = np.vstack(saidas).astype(np.float32)
        fins = (np.array(inicios) + palavra.JANELA_MEL) * 0.01
        return vet, fins


def janelas(vet, fins):
    """Todas as janelas de 16 vetores: (n, 16, 96) e o instante em que cada uma termina."""
    n = palavra.VETORES
    if len(vet) < n:
        return np.zeros((0, n, 96), np.float32), np.zeros(0)
    idx = np.arange(n - 1, len(vet))
    return np.stack([vet[i - n + 1:i + 1] for i in idx]), fins[idx]


# — dados ——————————————————————————————————————————————————————————————————————
def fundo_aleatorio(negativos, segundos):
    """Um fundo de casa: silêncio com chiado, ruído, ou fala (negativos) baixa."""
    n = int(round(SR * segundos))  # round: len(y)/SR*SR às vezes dá uma amostra a menos
    tipo = rng.random()
    base = rng.standard_normal(n) * 10 ** rng.uniform(-4.2, -2.6)
    if tipo < 0.45:
        fala = np.concatenate([ler(negativos[i]) for i in rng.integers(0, len(negativos), 3)])
        fala = np.tile(fala, int(np.ceil(n / len(fala))) + 1)[:n]
        base = base + fala * 10 ** rng.uniform(-1.6, -0.6)
    return base


def montar(x, negativos, antes, depois=0.5):
    pre = fundo_aleatorio(negativos, antes)
    pos = fundo_aleatorio(negativos, depois)
    return np.concatenate([pre, x, pos]), antes


def aumentar(x, negativos):
    # O volume de -20 a +15 dB (22/11/2026, medido): as chamadas ao vivo pelo
    # microfone direto do Windows chegam 10 a 20 dB mais altas que as gravações
    # (pico de -3 dB, quase estourando), e com -12 a +5 dB o detector pegou 2 de 24.
    x = x * 10 ** rng.uniform(-1.0, 0.75)
    if rng.random() < 0.3:
        x = eco(x)
    r = rng.random()
    if r < 0.35:
        fala = np.concatenate([ler(negativos[i]) for i in rng.integers(0, len(negativos), 4)])
        x = com_snr(x, fala, rng.uniform(3, 18))
    elif r < 0.6:
        x = com_snr(x, rng.standard_normal(len(x)), rng.uniform(8, 30))
    return np.clip(x, -1, 1)


def positivos_de(ext, arquivo, tempo, negativos, vezes):
    x = ler(arquivo)
    ini, fim = tempo if tempo else fim_por_energia(x)
    X, Y = [], []
    for _ in range(vezes):
        y, desloc = montar(aumentar(x, negativos), negativos, rng.uniform(0.6, 1.8))
        w, t = janelas(*ext.vetores(y))
        f, i0 = fim + desloc, ini + desloc
        pos = (t >= f + 0.0) & (t <= f + 0.32)
        neg = t < i0 + 0.12
        X += [w[pos], w[neg]]
        Y += [np.ones(pos.sum()), np.zeros(neg.sum())]
    return X, Y


def negativos_de(ext, arquivo, negativos, vezes):
    x = ler(arquivo)
    X = []
    for k in range(vezes):
        y, _ = montar(aumentar(x, negativos) if k else x, negativos, rng.uniform(0.3, 1.2))
        w, _ = janelas(*ext.vetores(y))
        X.append(w)
    return X


def fala_colada(negativos, n=5):
    """Várias frases negativas coladas, com pausas curtas e o fundo de casa: a
    fala corrida. Medido em 21/11/2026: cada negativo sozinho quase não
    disparava (7 de 245), mas em fila o fim de uma frase com o começo da outra
    formava "Solis" (51 alarmes em 10 min)."""
    partes = []
    for i in rng.integers(0, len(negativos), n):
        partes += [aumentar(ler(negativos[i]), negativos), fundo_aleatorio(negativos, rng.uniform(0.05, 0.6))]
    y = np.concatenate(partes)
    return np.clip(y + fundo_aleatorio(negativos, len(y) / SR)[:len(y)] * 0.5, -1, 1)


# — o modelo (numpy) ———————————————————————————————————————————————————————————
class Rede:
    def __init__(self, entrada=16 * 96, oculta=64):
        self.W1 = rng.standard_normal((entrada, oculta)).astype(np.float32) * np.sqrt(2 / entrada)
        self.b1 = np.zeros(oculta, np.float32)
        self.W2 = rng.standard_normal((oculta, 1)).astype(np.float32) * np.sqrt(1 / oculta)
        self.b2 = np.zeros(1, np.float32)
        self.media = np.zeros(entrada, np.float32)
        self.desvio = np.ones(entrada, np.float32)

    def nota(self, X):
        z = (X.reshape(len(X), -1) - self.media) / self.desvio
        h = np.maximum(z @ self.W1 + self.b1, 0)
        return 1 / (1 + np.exp(-(h @ self.W2 + self.b2)[:, 0]))

    def treinar(self, X, Y, epocas=40, lote=512, lr=1e-3, l2=1e-4, peso_neg=1.0, aval=None):
        X = X.reshape(len(X), -1)
        self.media, self.desvio = X.mean(0), X.std(0) + 1e-4
        Z = (X - self.media) / self.desvio
        params = [self.W1, self.b1, self.W2, self.b2]
        m = [np.zeros_like(p) for p in params]
        v = [np.zeros_like(p) for p in params]
        # A média dos pesos ao longo dos passos (EMA): medido em 21/11/2026, os
        # alarmes falsos pulavam de 2 pra 24 de uma época pra outra; a média
        # tira o tremido. É ela que fica no fim.
        media_pesos = [p.copy() for p in params]
        passo = 0
        pesos = np.where(Y > 0.5, 1.0, peso_neg).astype(np.float32)
        lr0 = lr
        for ep in range(epocas):
            lr = lr0 * 0.5 * (1 + np.cos(np.pi * ep / epocas))  # cai devagar até o fim
            ordem = rng.permutation(len(Z))
            perda = 0.0
            for k in range(0, len(Z), lote):
                b = ordem[k:k + lote]
                z, y, wt = Z[b], Y[b], pesos[b]
                if rng.random() < 1.0:  # um pouco de ruído na entrada (regulariza)
                    z = z + rng.standard_normal(z.shape).astype(np.float32) * 0.05
                pre = z @ self.W1 + self.b1
                h = np.maximum(pre, 0)
                p = 1 / (1 + np.exp(-(h @ self.W2 + self.b2)[:, 0]))
                p = np.clip(p, 1e-6, 1 - 1e-6)
                perda += float(np.sum(-wt * (y * np.log(p) + (1 - y) * np.log(1 - p))))
                g = (wt * (p - y) / len(b))[:, None]
                gW2 = h.T @ g + l2 * self.W2
                gb2 = g.sum(0)
                gh = (g @ self.W2.T) * (pre > 0)
                gW1 = z.T @ gh + l2 * self.W1
                gb1 = gh.sum(0)
                passo += 1
                for i, (p_, g_) in enumerate(zip(params, [gW1, gb1, gW2, gb2])):
                    m[i] = 0.9 * m[i] + 0.1 * g_
                    v[i] = 0.999 * v[i] + 0.001 * g_ ** 2
                    p_ -= lr * (m[i] / (1 - 0.9 ** passo)) / (np.sqrt(v[i] / (1 - 0.999 ** passo)) + 1e-8)
                    media_pesos[i] *= 0.998
                    media_pesos[i] += 0.002 * p_
            if aval and (ep % 5 == 4 or ep == epocas - 1):
                atuais = [p.copy() for p in params]
                for p_, mp in zip(params, media_pesos):
                    p_[...] = mp
                print(f'  época {ep + 1}: perda {perda / len(Z):.4f} · (média) {aval(self)}', flush=True)
                for p_, a in zip(params, atuais):
                    p_[...] = a
        for p_, mp in zip(params, media_pesos):
            p_[...] = mp

    def salvar(self, caminho):
        caminho.parent.mkdir(parents=True, exist_ok=True)
        np.savez(caminho, W1=self.W1, b1=self.b1, W2=self.W2, b2=self.b2, media=self.media, desvio=self.desvio)


# — medir ———————————————————————————————————————————————————————————————————————
def notas_do_audio(ext, rede, x):
    w, t = janelas(*ext.vetores(x))
    return rede.nota(w) if len(w) else np.zeros(0), t


PACIENCIA = 2   # notas altas seguidas pra acordar (o openWakeWord tem a mesma ideia)


def ativacoes(notas, t, limiar, refratario=1.5, paciencia=PACIENCIA):
    vezes, ultimo, seguidas = 0, -99.0, 0
    for n, s in zip(notas, t):
        seguidas = seguidas + 1 if n >= limiar else 0
        if seguidas >= paciencia and s - ultimo > refratario:
            vezes, ultimo, seguidas = vezes + 1, s, 0
    return vezes


def acordou(notas, limiar, paciencia=PACIENCIA):
    seguidas = 0
    for n in notas:
        seguidas = seguidas + 1 if n >= limiar else 0
        if seguidas >= paciencia:
            return True
    return False


def _grupos_no_tempo(arquivos, junto_s=3):
    """As gravações ao vivo de uma mesma chamada (salvas com 1 s de diferença) ficam juntas."""
    grupos, ultimo = [], None
    for a in arquivos:
        m = re.search(r'(\d{8})-(\d{2})(\d{2})(\d{2})', Path(a).name)
        t = (int(m[1]), int(m[2]) * 3600 + int(m[3]) * 60 + int(m[4])) if m else None
        if grupos and t and ultimo and t[0] == ultimo[0] and t[1] - ultimo[1] <= junto_s:
            grupos[-1].append(a)
        else:
            grupos.append([a])
        ultimo = t
    return grupos


def separar_ao_vivo(tempos):
    """As chamadas ao vivo: as do Whisper (confirmadas) — um terço das chamadas fica de
    fora pra medir —, e os disparos do detector, que só são positivos se o Whisper
    achar "Solis" neles (senão, são alarme falso: negativo)."""
    whisper = sorted(glob.glob(str(AMOSTRAS / 'vivo-whisper' / '*.wav')))
    grupos = _grupos_no_tempo(whisper)
    teste = [a for i, g in enumerate(grupos) if i % 3 == 1 for a in g]
    treino = [a for a in whisper if a not in teste]
    disparos = sorted(glob.glob(str(AMOSTRAS / 'vivo-palavra' / '*.wav')))
    falsos = [a for a in disparos if not tempos.get(a)]
    return treino + [a for a in disparos if tempos.get(a)], teste, falsos


def main():
    t0 = time.time()
    ext = Extrator()
    guardadas = {l.strip() for l in (TREINO / 'teste-local.txt').read_text(encoding='utf-8').splitlines() if l.strip()}
    reais = sorted(a for a in glob.glob(str(AMOSTRAS / '*' / '*.wav')) if '\\vivo-' not in a and '/vivo-' not in a)
    reais_treino = [a for a in reais if a not in guardadas]
    reais_teste = [a for a in reais if a in guardadas]
    vivos = sorted(glob.glob(str(AMOSTRAS / 'vivo-*' / '*.wav')))
    pos_tts = sorted(glob.glob(str(TREINO / 'positivos-tts' / '*.wav')))
    negs = sorted(glob.glob(str(TREINO / 'negativos-tts' / '*.wav')))
    # Negativos guardados pra medir: um a cada 7 (todas as frases e vozes aparecem dos dois lados).
    neg_teste = negs[::7]
    neg_treino = [a for i, a in enumerate(negs) if i % 7]
    print(f'reais: {len(reais_treino)} treino, {len(reais_teste)} guardadas · tts: {len(pos_tts)} · '
          f'negativos: {len(neg_treino)} treino, {len(neg_teste)} guardados', flush=True)

    print('marcando onde a palavra termina (Whisper turbo)...', flush=True)
    tempos = marcar_tempos(reais + pos_tts + vivos)
    sem = [a for a, v in tempos.items() if not v]
    print(f'  sem a palavra achada (fica a energia): {len(sem)} — {[Path(a).name for a in sem[:8]]}', flush=True)
    vivo_treino, vivo_teste, vivo_falsos = separar_ao_vivo(tempos)
    print(f'ao vivo: {len(vivo_treino)} treino, {len(vivo_teste)} guardadas pra medir, '
          f'{len(vivo_falsos)} disparos sem "Solis" (alarme falso)', flush=True)
    medir_o_de_hoje(ext, vivo_teste + vivo_treino, neg_teste)

    guardado = TREINO / 'janelas.npz'
    if guardado.exists() and '--de-novo' not in sys.argv:
        d = np.load(guardado)
        X, Y = d['X'], d['Y']
        print(f'  janelas guardadas: {len(X)} ({int(Y.sum())} positivas) — --de-novo refaz', flush=True)
    else:
        X, Y = extrair(ext, reais_treino, pos_tts, neg_treino, tempos, t0, vivo_treino, vivo_falsos)
        np.savez(guardado, X=X, Y=Y)
    return treinar_e_medir(ext, X, Y, reais_teste, neg_treino, neg_teste, t0, vivo_teste)


def medir_o_de_hoje(ext, vivos, neg_teste):
    """O detector instalado agora, nas chamadas ao vivo (o antes)."""
    if not SAIDA.exists() or not vivos:
        return
    d = np.load(SAIDA)
    rede = Rede()
    rede.W1, rede.b1, rede.W2, rede.b2, rede.media, rede.desvio = (d[k] for k in ('W1', 'b1', 'W2', 'b2', 'media', 'desvio'))
    for limiar in (0.5, 0.9):
        pegou = sum(acordou(notas_do_audio(ext, rede, montar(ler(a), neg_teste, 1.0)[0])[0], limiar) for a in vivos)
        print(f'  o detector de hoje, ao vivo (limiar {limiar}): {pegou}/{len(vivos)}', flush=True)


def extrair(ext, reais_treino, pos_tts, neg_treino, tempos, t0, vivo_treino=(), vivo_falsos=()):
    print('vetores...', flush=True)
    X, Y = [], []
    for i, a in enumerate(reais_treino):
        xs, ys = positivos_de(ext, a, tempos.get(a), neg_treino, 14)
        X += xs
        Y += ys
    # As chamadas ao vivo valem mais: é o microfone e a sala de verdade.
    for a in vivo_treino:
        xs, ys = positivos_de(ext, a, tempos.get(a), neg_treino, 40)
        X += xs
        Y += ys
    for a in vivo_falsos:  # o que o detector achou que era "Solis" e não era
        for w in negativos_de(ext, a, neg_treino, 20):
            X.append(w)
            Y.append(np.zeros(len(w)))
    for a in pos_tts:
        xs, ys = positivos_de(ext, a, tempos.get(a), neg_treino, 4)
        X += xs
        Y += ys
    for i, a in enumerate(neg_treino):
        for w in negativos_de(ext, a, neg_treino, 2):
            X.append(w)
            Y.append(np.zeros(len(w)))
        if i % 400 == 0:
            print(f'  negativos {i}/{len(neg_treino)}', flush=True)
    for _ in range(300):  # só fundo: silêncio, ruído, conversa baixa
        w, _ = janelas(*ext.vetores(fundo_aleatorio(neg_treino, 4.0)))
        X.append(w)
        Y.append(np.zeros(len(w)))
    for _ in range(900):  # a fala corrida: frases coladas, com as emendas entre elas
        w, _ = janelas(*ext.vetores(fala_colada(neg_treino)))
        X.append(w)
        Y.append(np.zeros(len(w)))
    X = np.concatenate([x for x in X if len(x)]).astype(np.float32)
    Y = np.concatenate([y for y in Y if len(y)]).astype(np.float32)
    print(f'  {len(X)} janelas: {int(Y.sum())} positivas, {int((1 - Y).sum())} negativas '
          f'({time.time() - t0:.0f} s)', flush=True)
    return X, Y


def treinar_e_medir(ext, X, Y, reais_teste, neg_treino, neg_teste, t0, vivo_teste=()):
    # O teste: as 32 guardadas (limpas e com fala por cima); os negativos guardados em fila (com
    # silêncio digital e com o fundo de casa); e a fala corrida que nunca entra no treino.
    teste_limpo = [montar(ler(a), neg_teste, 1.0)[0] for a in reais_teste]
    teste_barulho = [montar(np.clip(com_snr(ler(a), np.concatenate([ler(neg_teste[i]) for i in rng.integers(
        0, len(neg_teste), 4)]), 8), -1, 1), neg_teste, 1.0)[0] for a in reais_teste]
    fila = np.concatenate([np.concatenate([ler(a), np.zeros(int(SR * 0.4))]) for a in neg_teste])
    fila_casa = np.clip(fila + fundo_aleatorio(neg_teste, len(fila) / SR)[:len(fila)] * 0.5, -1, 1)
    corrida = [ler(a) for a in sorted(glob.glob(str(TREINO / 'fala-corrida' / '*.wav')))]
    corrida = np.concatenate(corrida) if corrida else np.zeros(SR)
    min_fila, min_corrida = len(fila) / SR / 60, len(corrida) / SR / 60
    # As janelas dos testes não dependem do modelo: tiradas uma vez só.
    j_limpo = [janelas(*ext.vetores(x))[0] for x in teste_limpo]
    j_barulho = [janelas(*ext.vetores(x))[0] for x in teste_barulho]
    j_falsos = [janelas(*ext.vetores(a)) for a in (fila, fila_casa, corrida)]
    j_vivo = [janelas(*ext.vetores(montar(ler(a), neg_teste, 1.0)[0]))[0] for a in vivo_teste]

    def aval(rede, limiar=0.5, detalhe=False):
        acertos = sum(acordou(rede.nota(w), limiar) for w in j_limpo)
        com_barulho = sum(acordou(rede.nota(w), limiar) for w in j_barulho)
        ao_vivo = sum(acordou(rede.nota(w), limiar) for w in j_vivo)
        falsos = [ativacoes(rede.nota(w), t, limiar) for w, t in j_falsos]
        txt = (f'guardadas {acertos}/{len(teste_limpo)} · com fala por cima {com_barulho}/{len(teste_barulho)} · '
               f'ao vivo (nunca vistas) {ao_vivo}/{len(j_vivo)} · '
               f'falsos: fila {falsos[0]}, fila com fundo {falsos[1]} ({min_fila:.1f} min cada), '
               f'fala corrida {falsos[2]} ({min_corrida:.1f} min)')
        return (acertos, com_barulho, falsos, ao_vivo) if detalhe else txt

    def cacar(rede, limiar=0.15, rodadas=400):
        """As janelas negativas que o modelo confunde (fala colada nova, e o
        antes da palavra nos positivos): voltam pro treino com mais peso."""
        duras = []
        for _ in range(rodadas):
            w, _ = janelas(*ext.vetores(fala_colada(neg_treino, 6)))
            if len(w):
                duras.append(w[rede.nota(w) >= limiar])
        duras = [d for d in duras if len(d)]
        return np.concatenate(duras) if duras else np.zeros((0, palavra.VETORES, 96), np.float32)

    print('treinando...', flush=True)
    peso_neg = float(Y.sum() / max((1 - Y).sum(), 1)) * 4
    rede = Rede()
    rede.treinar(X, Y, epocas=30, peso_neg=max(peso_neg, 0.05), aval=aval)
    for rodada in (1, 2):
        duras = cacar(rede)
        print(f'caça {rodada}: {len(duras)} janelas negativas confundidas — voltam com peso', flush=True)
        if len(duras):
            X = np.concatenate([X, np.repeat(duras, 4, axis=0)])
            Y = np.concatenate([Y, np.zeros(len(duras) * 4, np.float32)])
        rede = Rede()
        rede.treinar(X, Y, epocas=30, peso_neg=max(peso_neg, 0.05), aval=aval)
    print('limiares:', flush=True)
    resultado = {}
    for limiar in (0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 0.98):
        a, b, f, v = aval(rede, limiar, detalhe=True)
        resultado[limiar] = (int(a), int(b), [int(x) for x in f], int(v))
        print(f'  {limiar}: guardadas {a}/{len(teste_limpo)} · com fala por cima {b}/{len(teste_barulho)} · '
              f'ao vivo {v}/{len(j_vivo)} · falsos fila {f[0]}, fila com fundo {f[1]}, fala corrida {f[2]}', flush=True)
    horas = (2 * min_fila + min_corrida) / 60
    if '--so-medir' in sys.argv:
        rede.salvar(TREINO / 'solis-novo.npz')
        print('medido e guardado só em _treino-solis/solis-novo.npz (--so-medir)')
        return
    rede.salvar(SAIDA)
    # Uma cópia na pasta do treino: o que o terminal do Claude grava em %LOCALAPPDATA%
    # pode não chegar ao Windows de verdade (a caixa de areia); o Solis instala dali.
    rede.salvar(TREINO / 'solis.npz')
    (TREINO / 'resultado-local.json').write_text(json.dumps({'limiares': resultado, 'minutos_negativos': horas * 60},
                                                            indent=1), encoding='utf-8')
    print(f'salvo em {SAIDA} ({time.time() - t0:.0f} s)')


if __name__ == '__main__':
    main()
