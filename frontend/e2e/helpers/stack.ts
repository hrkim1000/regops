import { execFileSync } from 'node:child_process';
import { resolve } from 'node:path';

const REPO_ROOT = resolve(__dirname, '../../..');

/**
 * Run the E2E fixture script inside the stack and read back its JSON.
 *
 * It runs in the `regulation` container because that is where `/scripts` is mounted — and because
 * it is the container `regulation`'s own diff stage would be dispatching from when it tells
 * `assistant` an amendment landed. The script never writes across a seam the services do not
 * already write across: it seeds an answer row and sends a task by name.
 */
export function fixture<T>(...args: string[]): T {
  const stdout = execFileSync(
    'docker',
    ['compose', 'exec', '-T', 'regulation', 'python', '/scripts/e2e_fixture.py', ...args],
    { cwd: REPO_ROOT, encoding: 'utf8' },
  );
  // The script prints one JSON object last; anything before it is a library's logging.
  const line = stdout
    .trim()
    .split('\n')
    .reverse()
    .find((candidate) => candidate.trimStart().startsWith('{'));
  if (!line) throw new Error(`e2e_fixture.py ${args.join(' ')} printed no JSON:\n${stdout}`);
  return JSON.parse(line) as T;
}
