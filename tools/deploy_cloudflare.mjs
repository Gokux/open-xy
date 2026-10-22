import {spawnSync} from 'node:child_process';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {build} from 'vite';

const root = fileURLToPath(new URL('../', import.meta.url));
let directory;
await build({configFile:resolve(root, 'vite.config.mjs'), mode:'release', plugins:[{
  name:'open-xy-deploy-output',
  configResolved(config) { directory = resolve(config.root, config.build.outDir); },
}]});
const result = spawnSync(process.execPath, [resolve(root, 'node_modules/wrangler/bin/wrangler.js'),
  'deploy', ...process.argv.slice(2), '--assets', directory],
  {cwd:root, stdio:'inherit', windowsHide:true});
if (result.error) throw result.error;
process.exitCode = result.status ?? 1;
