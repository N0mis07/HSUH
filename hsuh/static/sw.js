// Installable, online-only PWA. Deliberately no cache, push or background sync.
// Chats, API results and authentication never enter Cache Storage or IndexedDB.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', event => {
  if (new URL(event.request.url).origin === self.location.origin) {
    event.respondWith(fetch(event.request));
  }
});
