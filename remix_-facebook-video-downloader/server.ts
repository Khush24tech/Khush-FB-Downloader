import { spawn } from 'child_process';

console.log('Spawning Python FastAPI Server on port 3000...');

const child = spawn('python3', [
  '-m', 'uvicorn', 'api.download:app',
  '--host', '0.0.0.0',
  '--port', '3000'
], {
  stdio: 'inherit'
});

child.on('close', (code) => {
  console.log(`Python server exited with code ${code}`);
  process.exit(code ?? 1);
});
