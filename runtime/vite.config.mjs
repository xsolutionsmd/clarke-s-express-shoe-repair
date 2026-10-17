// Launcher-only development integration; the frontend's build and preview stay unchanged.
export default {
  server: {
    headers: { 'X-Robots-Tag': 'noindex, nofollow' },
  },
  plugins: [{
    name: 'launcher-health-and-revision',
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const path = request.url?.split('?')[0];
        if (path !== '/health' && path !== '/version.json') return next();
        response.setHeader('Cache-Control', 'no-store');
        response.setHeader('X-Robots-Tag', 'noindex, nofollow');
        response.setHeader('Content-Type', path === '/health' ? 'text/plain' : 'application/json');
        response.end(path === '/health' ? 'ok\n' : JSON.stringify({ revision: process.env.APP_REVISION || 'unknown' }));
      });
    },
  }],
};
