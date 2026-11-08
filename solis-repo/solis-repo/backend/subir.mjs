// Sobe o servidor do Solis com o Python do .venv — é o `npm run backend`.
//
// Antes o script chamava `python` do PATH, e sem o .venv ativado o servidor
// subia com o Python do sistema, com outras bibliotecas (visto no notebook,
// 1º/11/2026). Aqui o .venv é procurado direto, e sem ele o servidor NÃO sobe:
// melhor parar dizendo o que fazer do que rodar com o Python errado.
//
//   npm run backend                 # 127.0.0.1:8765, recarregando ao salvar
//   npm run backend -- --port 8766  # o que vier depois do -- vai pro uvicorn
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const pasta = dirname(fileURLToPath(import.meta.url));
const python = [join(pasta, '.venv', 'Scripts', 'python.exe'), join(pasta, '.venv', 'bin', 'python')].find(existsSync);

if (!python) {
  console.error(
    'O servidor do Solis precisa do .venv em backend/, e ele não existe.\n' +
      'Uma vez só, na pasta backend:\n' +
      '  python -m venv .venv\n' +
      '  .venv\\Scripts\\Activate.ps1   (no Linux: source .venv/bin/activate)\n' +
      '  pip install -r requirements.txt -r requirements-dev.txt',
  );
  process.exit(1);
}

// Opção repetida no uvicorn vale a última: um --port depois do -- troca a padrão.
const args = ['-m', 'uvicorn', 'solis.main:app', '--host', '127.0.0.1', '--port', '8765', '--reload', ...process.argv.slice(2)];
const servidor = spawn(python, args, { cwd: pasta, stdio: 'inherit' });
servidor.on('exit', (codigo, sinal) => process.exit(sinal ? 1 : (codigo ?? 0)));
for (const sinal of ['SIGINT', 'SIGTERM']) process.on(sinal, () => servidor.kill(sinal));
