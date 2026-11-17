"""O modo Conversa (conversa_voz.py): a ponte entre a tela e o Gemini Live, com um
Gemini falso — nenhum teste fala com o Google."""
import asyncio
from types import SimpleNamespace as N

from fastapi.testclient import TestClient

from solis import banco, conversa_voz, main


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
