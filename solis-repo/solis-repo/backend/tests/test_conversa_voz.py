"""O modo Conversa (conversa_voz.py): a ponte entre a tela e o Gemini Live, com um
Gemini falso — nenhum teste fala com o Google."""
import asyncio
import io
from types import SimpleNamespace as N

from fastapi.testclient import TestClient

from solis import ativacao, banco, conversa_voz, main


def msg(ouviu=None, disse=None, audio=None, interrompido=False, fim=False):
    sc = N(
        input_transcription=N(text=ouviu) if ouviu else None,
        output_transcription=N(text=disse) if disse else None,
        model_turn=N(parts=[N(inline_data=N(data=audio))]) if audio else None,
        interrupted=interrompido,
        turn_complete=fim,
    )
    return N(server_content=sc)


class SessaoFalsa:
    """Devolve o roteiro e depois fica esperando, como a de verdade."""

    def __init__(self, roteiro):
        self.roteiro = list(roteiro)
        self.recebido = []

    async def send_realtime_input(self, audio):
        self.recebido.append(audio.data)

    async def receive(self):
        while self.roteiro:
            yield self.roteiro.pop(0)
            await asyncio.sleep(0)
        await asyncio.Event().wait()


def conduzir(sessao, da_tela, silencio_fim=5.0, relogio=None):
    saida_audio, saida, turnos = [], [], []
    fila = list(da_tela)

    async def receber():
        if fila:
            item = fila.pop(0)
            if item == 'espera':
                await asyncio.sleep(0.05)
                return {}
            return item
        await asyncio.Event().wait()

    async def mandar_audio(b):
        saida_audio.append(b)

    async def mandar(d):
        saida.append(d)

    async def ao_turno(f, r):
        turnos.append((f, r))

    async def rodar():
        return await conversa_voz.conduzir(sessao, receber, mandar_audio, mandar, ao_turno,
                                           silencio_fim=silencio_fim, **({'relogio': relogio} if relogio else {}))
    motivo = asyncio.run(rodar())
    return motivo, saida_audio, saida, turnos


def test_uma_troca_vai_e_volta_e_fica_salva_como_turno():
    sessao = SessaoFalsa([
        msg(ouviu='Que dia '), msg(ouviu='é hoje?'), msg(audio=b'\x01\x02'), msg(disse='Hoje é segunda.'),
        msg(audio=b'\x03\x04'), msg(fim=True),
    ])
    motivo, audio, saida, turnos = conduzir(sessao, [{'audio': b'mic1'}, {'audio': b'mic2'}, 'espera', 'espera',
                                                     {'fim': True}])
    assert motivo == 'fim'
    assert sessao.recebido == [b'mic1', b'mic2']  # o microfone chegou ao Gemini
    assert audio == [b'\x01\x02', b'\x03\x04']  # a voz dele chegou à tela
    assert turnos == [('Que dia é hoje?', 'Hoje é segunda.')]
    assert {'tipo': 'turno', 'fala': 'Que dia é hoje?', 'resposta': 'Hoje é segunda.'} in saida
    assert {'tipo': 'ouviu', 'texto': 'Que dia é hoje?'} in saida


def test_interromper_avisa_a_tela_pra_parar_de_tocar():
    sessao = SessaoFalsa([msg(audio=b'\x01'), msg(interrompido=True), msg(fim=True)])
    _, _, saida, _ = conduzir(sessao, ['espera', 'espera', {'fim': True}])
    assert {'tipo': 'interrompido'} in saida


def test_trinta_segundos_sem_ninguem_falar_acaba():
    agora = {'t': 0.0}

    def relogio():
        agora['t'] += 1.0  # cada consulta, um segundo
        return agora['t']
    motivo, *_ = conduzir(SessaoFalsa([]), [], silencio_fim=5.0, relogio=relogio)
    assert motivo == 'silencio'


def test_a_tela_fechando_acaba():
    motivo, *_ = conduzir(SessaoFalsa([]), [{'saiu': True}])
    assert motivo == 'saiu'


def test_o_contexto_nao_leva_nada_privado():
    banco.adicionar_memoria('Gosta de café sem açúcar.', 'Gostos', False, None)
    banco.adicionar_memoria('Faz terapia às quintas.', 'Saúde', False, None, privada=True)
    cid = banco.nova_conversa()
    banco.adicionar(cid, 'pessoa', 'Me conta do meu exame.', privada=True)
    banco.adicionar(cid, 'pessoa', 'Qual a capital da França?')
    s = conversa_voz.sistema(cid)
    assert 'café sem açúcar' in s and 'capital da França' in s
    assert 'terapia' not in s and 'exame' not in s
    assert 'Nunca diga que fez algo' in s


def test_turno_salvo_vira_mensagens_e_o_privado_fica_marcado():
    cid = banco.nova_conversa()
    conversa_voz.salvar_turno(cid, 'Isso é privado: meu salário é tal.', 'Entendi.')
    m = banco.mensagens(cid)
    assert [(x['papel'], bool(x['privada'])) for x in m] == [('pessoa', True), ('solis', False)]
    assert m[1]['cerebro'] == 'gemini-live'


def test_rota_sem_a_chave_do_gemini_avisa_e_fecha():
    c = TestClient(main.app)
    with c.websocket_connect('/conversa-voz') as ws:
        assert ws.receive_json()['tipo'] == 'erro'


# — A reserva (Groq), com as peças falsas: nada sai pra nuvem ————————————————————

def _tom(segundos, tom=True):
    import array
    import math
    taxa = ativacao.TAXA
    n = int(segundos * taxa) // 512 * 512
    if not tom:
        return array.array('h', [0] * n).tobytes()
    return array.array('h', [int(8000 * math.sin(2 * math.pi * 300 * i / taxa)) for i in range(n)]).tobytes()


def _fala():
    """Um pedido: o silêncio do começo (o ruído da sala, aprendido), a fala e o
    silêncio do fim, em pedaços como os do microfone."""
    audio = _tom(conversa_voz.APRENDER_PISO_S + 0.2, tom=False) + _tom(1.0) + _tom(ativacao.FIM_SILENCIO + 0.3, tom=False)
    return [{'audio': audio[i:i + 4096]} for i in range(0, len(audio), 4096)]


def reserva(da_tela, texto='Qual a capital da França?', resposta='Paris. Quer saber mais alguma coisa?',
            falha=None, voz_s=0.1, silencio_fim=5.0, local=None):
    saida_audio, saida, turnos, pedidos = [], [], [], []
    fila = list(da_tela)

    async def receber():
        if fila:
            item = fila.pop(0)
            if item == 'espera':
                await asyncio.sleep(0.05)
                return {}
            return item
        await asyncio.Event().wait()

    async def mandar_audio(b):
        saida_audio.append(b)

    async def mandar(d):
        saida.append(d)

    async def ao_turno(f, r, c):
        turnos.append((f, r, c))

    async def transcrever(tipo, wav):
        pedidos.append(tipo)
        return texto

    async def responder(conversa, t):
        if falha:
            raise falha
        return resposta

    async def falar(t, conversa):
        yield b'\x00\x00' * int(conversa_voz.TAXA_SAIDA * voz_s)

    async def rodar():
        return await conversa_voz.conduzir_reserva(
            None, receber, mandar_audio, mandar, ao_turno, local=local, silencio_fim=silencio_fim,
            ouvido=ativacao.Escuta(whisper=True), transcrever=transcrever, responder=responder, falar=falar)
    motivo = asyncio.run(rodar())
    return motivo, saida_audio, saida, turnos, pedidos


def test_reserva_uma_troca_vai_e_volta_e_fica_salva_como_turno():
    motivo, audio, saida, turnos, pedidos = reserva(_fala() + ['espera'] * 20 + [{'fim': True}])
    assert motivo == 'fim' and pedidos == ['comando']
    assert {'tipo': 'ouviu', 'texto': 'Qual a capital da França?'} in saida
    assert {'tipo': 'disse', 'texto': 'Paris. Quer saber mais alguma coisa?'} in saida
    assert turnos == [('Qual a capital da França?', 'Paris. Quer saber mais alguma coisa?', 'groq')]
    assert audio and all(len(a) == 2 * int(conversa_voz.TAXA_SAIDA * 0.1) for a in audio)


def test_reserva_o_microfone_nao_conta_enquanto_ele_fala():
    """A voz dele sai das caixas: o que o microfone pega nesse tempo não vira pedido."""
    motivo, _, _, turnos, pedidos = reserva(_fala() + _fala() + ['espera'] * 30 + [{'fim': True}], voz_s=1.5)
    assert motivo == 'fim' and pedidos == ['comando'] and len(turnos) == 1


def test_reserva_o_privado_responde_o_modelo_daqui():
    chamado = []

    async def local(instrucao, texto):
        chamado.append(texto)
        return 'Anotado só aqui.'
    _, _, saida, turnos, _ = reserva(_fala() + ['espera'] * 20 + [{'fim': True}],
                                     texto='Isso é privado: meu salário é tal.', local=local)
    assert chamado == ['Isso é privado: meu salário é tal.']
    assert turnos == [('Isso é privado: meu salário é tal.', 'Anotado só aqui.', 'local')]


def test_reserva_sem_o_modelo_daqui_o_privado_nao_vai_pra_nuvem():
    _, _, _, turnos, _ = reserva(_fala() + ['espera'] * 20 + [{'fim': True}], texto='Isso é privado: meu exame.',
                                 falha=AssertionError('não podia chamar a nuvem'))
    assert turnos == [('Isso é privado: meu exame.', conversa_voz.FRASE_PRIVADO, 'local')]


def test_reserva_a_groq_caindo_diz_que_nao_deu():
    _, _, _, turnos, _ = reserva(_fala() + ['espera'] * 20 + [{'fim': True}], falha=RuntimeError('429'))
    assert turnos[0][1] == conversa_voz.FRASE_FALHOU


def test_reserva_sem_ninguem_falar_acaba():
    motivo, *_ = reserva([], silencio_fim=0.3)
    assert motivo == 'silencio'


def test_reserva_a_tela_fechando_acaba():
    motivo, *_ = reserva([{'saiu': True}])
    assert motivo == 'saiu'


def test_a_voz_vira_o_pcm_que_a_tela_toca():
    import wave
    b = io.BytesIO()
    with wave.open(b, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(_tom(1.0))
    pcm = conversa_voz.pcm24(b.getvalue())
    # ~1 s a 24 kHz, 16 bits.
    assert abs(len(pcm) / 2 / conversa_voz.TAXA_SAIDA - 1.0) < 0.05


def test_o_mp3_aos_pedacos_vira_pcm_desde_o_primeiro():
    import av
    import numpy as np
    b = io.BytesIO()
    with av.open(b, 'w', format='mp3') as o:
        s = o.add_stream('libmp3lame', rate=44100, layout='mono')
        tom = (np.sin(2 * np.pi * 300 * np.arange(44100) / 44100) * 20000).astype(np.int16).reshape(1, -1)
        q = av.AudioFrame.from_ndarray(tom, format='s16', layout='mono')
        q.sample_rate = 44100
        for p in [*s.encode(q), *s.encode(None)]:
            o.mux(p)
    mp3, conversor = b.getvalue(), conversa_voz.Mp3EmPcm()
    pedacos = [conversor(mp3[i:i + 700]) for i in range(0, len(mp3), 700)]
    assert pedacos[1]  # o som começa logo, sem esperar o mp3 inteiro
    total = sum(map(len, pedacos)) + len(conversor.fim())
    assert abs(total / 2 / conversa_voz.TAXA_SAIDA - 1.0) < 0.1


def test_rota_sem_o_gemini_segue_pela_reserva(monkeypatch):
    monkeypatch.setattr(conversa_voz, 'reserva_disponivel', lambda: True)
    chamada = []

    async def conduzir_reserva(conversa, receber, mandar_audio, mandar, ao_turno, local=None):
        chamada.append(conversa)
        return 'fim'
    monkeypatch.setattr(conversa_voz, 'conduzir_reserva', conduzir_reserva)
    c = TestClient(main.app)
    with c.websocket_connect('/conversa-voz') as ws:
        assert ws.receive_json()['tipo'] == 'pronta'
        assert ws.receive_json() == {'tipo': 'reserva'}
        assert ws.receive_json() == {'tipo': 'fim', 'motivo': 'fim'}
    assert len(chamada) == 1


def test_rota_o_gemini_caindo_segue_pela_reserva_e_fica_de_lado(monkeypatch):
    monkeypatch.setattr(conversa_voz, '_gemini_fora', {'ate': 0.0})
    monkeypatch.setattr(conversa_voz, 'reserva_disponivel', lambda: True)
    abertos = []

    class Caiu:
        async def __aenter__(self):
            raise RuntimeError('1011 quota exceeded')

        async def __aexit__(self, *_):
            return False

    def abrir(conversa, voz):
        abertos.append(conversa)
        return Caiu()
    monkeypatch.setattr(conversa_voz, 'abrir', abrir)

    async def conduzir_reserva(*_, **__):
        return 'fim'
    monkeypatch.setattr(conversa_voz, 'conduzir_reserva', conduzir_reserva)
    c = TestClient(main.app)
    for _ in range(2):
        with c.websocket_connect('/conversa-voz') as ws:
            assert ws.receive_json()['tipo'] == 'pronta'
            assert ws.receive_json() == {'tipo': 'reserva'}
            assert ws.receive_json()['tipo'] == 'fim'
    # Caiu uma vez: a segunda conversa já nem tenta o Gemini.
    assert len(abertos) == 1 and conversa_voz.gemini_descansando()


def test_reserva_aprende_o_ruido_da_sala_antes_de_ouvir():
    """18/11/2026: com o piso padrão, o ruído da gravação contou como fala e o
    pedido não acabava. O começo do microfone ensina o ruído."""
    import array
    import random
    rnd = random.Random(1)
    ruido = lambda s: array.array('h', [rnd.randint(-300, 300) for _ in range(int(s * ativacao.TAXA) // 512 * 512)]).tobytes()
    tom = _tom(1.0)
    mistura = array.array('h', tom)
    r = array.array('h', ruido(1.0))
    audio = ruido(conversa_voz.APRENDER_PISO_S + 0.2) + array.array('h', (a + b for a, b in zip(mistura, r))).tobytes()         + ruido(ativacao.FIM_SILENCIO + 0.3)
    _, _, _, turnos, pedidos = reserva([{'audio': audio[i:i + 4096]} for i in range(0, len(audio), 4096)]
                                       + ['espera'] * 20 + [{'fim': True}])
    assert pedidos == ['comando'] and len(turnos) == 1
