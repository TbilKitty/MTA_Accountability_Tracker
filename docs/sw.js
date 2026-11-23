// Cleanup only. The tracker briefly shipped as a home-screen app (Nov 23, 2026).
// Browsers that saved that version load this file on their next visit; it clears
// the saved copy and removes itself, so the site behaves like a normal web page.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => k.startsWith('mta-tracker-')).map(k => caches.delete(k)));
    await self.registration.unregister();
    const clients = await self.clients.matchAll({ type: 'window' });
    clients.forEach(c => c.navigate(c.url));
  })());
});
