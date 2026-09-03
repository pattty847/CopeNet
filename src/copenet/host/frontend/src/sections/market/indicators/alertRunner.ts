import { evaluateAlertRequest } from './alertEvaluator';

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (chunk: string) => {
  input += chunk;
  if (input.length > 8_000_000) { process.stderr.write('Evaluator input too large'); process.exit(1); }
});
process.stdin.on('end', () => {
  try { process.stdout.write(JSON.stringify(evaluateAlertRequest(JSON.parse(input)))); }
  catch (error) { process.stdout.write(JSON.stringify({ error: error instanceof Error ? error.message : 'Evaluator failed' })); process.exitCode = 1; }
});
