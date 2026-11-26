"""Quanto de RAM o servidor do Solis ocupa carregado, sem modelo local nenhum (Windows).

26/11/2026: 67 MB depois de importar o main (só o numpy dos pesados carrega; Whisper e Kokoro
só entram quando usados). Rodar de dentro de backend/, no PowerShell:
    $env:PYTHONPATH = '.'; .venv/Scripts/python ../design/nuvem/medir_ram.py
"""
import ctypes
import ctypes.wintypes as w
import os
import sys
import tempfile
import time

os.environ['SOLIS_BANCO'] = os.path.join(tempfile.mkdtemp(), 'solis.db')
os.environ['SOLIS_AVISOS'] = '0'


class PMC(ctypes.Structure):
    _fields_ = [('cb', w.DWORD), ('PageFaultCount', w.DWORD), ('PeakWorkingSetSize', ctypes.c_size_t),
                ('WorkingSetSize', ctypes.c_size_t), ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPagedPoolUsage', ctypes.c_size_t), ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
                ('QuotaNonPagedPoolUsage', ctypes.c_size_t), ('PagefileUsage', ctypes.c_size_t),
                ('PeakPagefileUsage', ctypes.c_size_t), ('PrivateUsage', ctypes.c_size_t)]


def ram():
    c = PMC()
    c.cb = ctypes.sizeof(c)
    k = ctypes.windll.kernel32
    k.GetCurrentProcess.restype = w.HANDLE
    k.K32GetProcessMemoryInfo.argtypes = [w.HANDLE, ctypes.POINTER(PMC), w.DWORD]
    k.K32GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(c), c.cb)
    return c.WorkingSetSize / 2**20, c.PrivateUsage / 2**20


print(f'python puro: {ram()[0]:.0f} MB')
t = time.perf_counter()
from solis import main  # noqa: E402
print(f'importado em {time.perf_counter() - t:.1f} s: {ram()[0]:.0f} MB (privada {ram()[1]:.0f} MB)')
pesados = [m for m in ('faster_whisper', 'ctranslate2', 'kokoro_onnx', 'onnxruntime', 'torch', 'cv2',
                       'pvporcupine', 'google.genai', 'claude_agent_sdk', 'trafilatura', 'numpy')
           if m in sys.modules]
print('carregados:', ', '.join(pesados))
from solis import banco  # noqa: E402
banco.conectar() if hasattr(banco, 'conectar') else None
print(f'com o banco: {ram()[0]:.0f} MB')
