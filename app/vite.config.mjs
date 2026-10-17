// Vite build for the Clarke's Express site: four HTML shells, shared partials, and a
// development proxy/route map that mirrors the Flask shell allowlist in docs/API.md.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';

const root = fileURLToPath(new URL('.', import.meta.url));
const apiOrigin = process.env.CLARKE_API_ORIGIN || 'http://127.0.0.1:8081';
const uuid = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}';

// Frontend route -> built HTML shell. Flask serves the same mapping in runtime.
export const shellRoutes = [
  [/^\/$/, 'index.html'],
  [/^\/repair-request(?:\/complete)?\/?$/, 'repair-request.html'],
  [/^\/repair-status\/?$/, 'repair-status.html'],
  [new RegExp(`^/admin/(?:login|invite|requests|requests/new|requests/${uuid}|settings|locations|notices|team|emails|emails/outbox/${uuid}|audit)/?$`, 'i'), 'admin.html'],
];

function partials() {
  const read = name => readFileSync(resolve(root, 'src/partials', `${name}.html`), 'utf8');
  return {
    name: 'clarke-partials',
    transformIndexHtml: {
      order: 'pre',
      handler: html => html.replace(/<!--\s*partial:([a-z-]+)\s*-->/g, (_, name) => read(name)),
    },
  };
}

function shellRewrite() {
  return {
    name: 'clarke-shell-routes',
    configureServer(server) {
      server.middlewares.use((request, _response, next) => {
        const [path, query = ''] = (request.url || '/').split('?');
        const match = shellRoutes.find(([pattern]) => pattern.test(path));
        if (match && path !== `/${match[1]}`) request.url = `/${match[1]}${query ? `?${query}` : ''}`;
        next();
      });
    },
  };
}

const proxy = Object.fromEntries(['/api/', '/oauth/', '/health', '/version.json']
  .map(prefix => [prefix, { target: apiOrigin, changeOrigin: false, xfwd: false }]));

export default {
  appType: 'mpa',
  plugins: [partials(), shellRewrite()],
  server: { proxy, headers: { 'X-Robots-Tag': 'noindex, nofollow' } },
  preview: { proxy },
  build: {
    target: 'es2022',
    assetsInlineLimit: 0,
    rollupOptions: {
      input: {
        index: resolve(root, 'index.html'),
        'repair-request': resolve(root, 'repair-request.html'),
        'repair-status': resolve(root, 'repair-status.html'),
        admin: resolve(root, 'admin.html'),
      },
    },
  },
};
