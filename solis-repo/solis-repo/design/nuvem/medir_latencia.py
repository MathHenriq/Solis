"""Tempo de ida e volta (conexão TCP) do PC do Matheus até as regiões candidatas e as APIs.

26/11/2026, mediana de 7: Brasil 31–38 ms (Oracle Vinhedo e São Paulo, AWS e Vultr São Paulo),
EUA 132–162 ms, Alemanha 205 ms; as APIs (Groq, Gemini, Anthropic, OpenRouter) 23–36 ms.
Rodar: python design/nuvem/medir_latencia.py
"""
import socket
import statistics
import time

ALVOS = {
    'Oracle · São Paulo': 'objectstorage.sa-saopaulo-1.oraclecloud.com',
    'Oracle · Vinhedo': 'objectstorage.sa-vinhedo-1.oraclecloud.com',
    'Oracle · Ashburn (EUA)': 'objectstorage.us-ashburn-1.oraclecloud.com',
    'AWS · São Paulo': 'ec2.sa-east-1.amazonaws.com',
    'AWS · Virgínia (EUA)': 'ec2.us-east-1.amazonaws.com',
    'Vultr · São Paulo': 'sao-br-ping.vultr.com',
    'Vultr · Miami': 'fl-us-ping.vultr.com',
    'Hetzner · Ashburn (EUA)': 'ash-speed.hetzner.com',
    'Hetzner · Alemanha': 'fsn1-speed.hetzner.com',
    'Google Cloud · Iowa (EUA)': 'storage.us-central1.rep.googleapis.com',
    'Google Cloud · Carolina do Sul (EUA)': 'storage.us-east1.rep.googleapis.com',
    'API · Groq': 'api.groq.com',
    'API · Gemini': 'generativelanguage.googleapis.com',
    'API · Anthropic': 'api.anthropic.com',
    'API · OpenRouter': 'openrouter.ai',
}


def rtt(host, vezes=7):
    ip = socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
    tempos = []
    for _ in range(vezes):
        t = time.perf_counter()
        with socket.create_connection((ip, 443), timeout=5):
            tempos.append((time.perf_counter() - t) * 1000)
        time.sleep(0.15)
    return ip, statistics.median(tempos), min(tempos)


for nome, host in ALVOS.items():
    try:
        ip, med, mn = rtt(host)
        print(f'{nome:40s} {med:6.0f} ms (mínimo {mn:4.0f})  {ip}')
    except Exception as e:  # noqa: BLE001
        print(f'{nome:40s} falhou: {type(e).__name__} {e}')
