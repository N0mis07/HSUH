import { build } from 'esbuild';
import { readFile, writeFile } from 'node:fs/promises';
await build({
  entryPoints: ['frontend/openui.tsx'], outfile: 'hsuh/static/openui.js',
  bundle: true, format: 'esm', minify: true, legalComments: 'eof',
  define: { 'process.env.NODE_ENV': '"production"' },
});
// Normalize the SDK's published documentation placeholder to an example domain.
// This exact fixture string is not a user identity and is not used by our library.
const output='hsuh/static/openui.js';
await writeFile(output,(await readFile(output,'utf8')).replaceAll(/your@email[.]com/g,'you@example.com'));
const { library } = await import('../hsuh/static/openui.js?build=' + Date.now());
const prompt=library.prompt({
  preamble:'You may render useful facts, comparisons and interactive checklists as OpenUI. Use only supplied facts; never invent live server readings. Ordinary answers can remain plain text.',
  additionalRules:['Wrap the complete program in one fenced openui code block. Keep it under 24000 characters and 150 lines. Only use the components listed here. No Query, Mutation, tool providers, remote URLs or external actions. The root must be Stack.'],
  examples:['root = Stack([Heading("Example checklist"), Checklist(["Read the requirements", "Verify the result"])])'],
});
await writeFile('hsuh/openui-prompt.txt',prompt);
const packages=['react','react-dom','scheduler','zod','@openuidev/react-lang','@openuidev/lang-core','@openuidev/devtools','@openuidev/observability'];
const notices=[];
for(const name of packages)notices.push(name+'\n'+await readFile('node_modules/'+name+'/LICENSE','utf8'));
await writeFile('hsuh/static/licenses.txt',notices.join('\n\n------------------------------\n\n'));
