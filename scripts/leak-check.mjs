import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
const root = new URL('../public/', import.meta.url).pathname;
const patterns = [/\/Users\/adrian/i, /misteradrian/i, /alumley007/i, /pregnancy/i, /medical/i, /stdout/i, /stderr/i, /workdir/i, /OpenClaw/i, /bishop-brain/i, /familyos/i, /operator stack/i, /mission control/i];
let failed = false;
function walk(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    const st = statSync(path);
    if (st.isDirectory()) walk(path);
    else {
      const text = readFileSync(path, 'utf8');
      for (const pattern of patterns) {
        if (pattern.test(text)) {
          console.error(`leak pattern ${pattern} in ${path}`);
          failed = true;
        }
      }
    }
  }
}
walk(root);
if (failed) process.exit(1);
console.log('public leak check passed');
