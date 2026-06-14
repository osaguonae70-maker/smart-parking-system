const CACHE_NAME = 'nsuk-smart-parking-v1';

const PRECACHE_URLS = [
    '/',
    '/portal',
    '/admin-login',
    '/static/css/style.css',
    '/static/js/main.js',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js',
    'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',
    'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',
    'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css'
];

self.addEventListener('install', (event) => {
    event.waitUntil((async () => {
        const cache = await caches.open(CACHE_NAME);
        await Promise.allSettled(
            PRECACHE_URLS.map(async (url) => {
                try {
                    const response = await fetch(url, { cache: 'no-cache' });
                    if (response.ok || response.type === 'opaque') {
                        await cache.put(url, response.clone());
                    }
                } catch (error) {
                    // Ignore failed pre-cache entries and continue installation.
                }
            })
        );
        await self.skipWaiting();
    })());
});

self.addEventListener('activate', (event) => {
    event.waitUntil((async () => {
        const keys = await caches.keys();
        await Promise.all(
            keys
                .filter((key) => key !== CACHE_NAME)
                .map((key) => caches.delete(key))
        );
        await self.clients.claim();
    })());
});

self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') {
        return;
    }

    event.respondWith((async () => {
        const cache = await caches.open(CACHE_NAME);

        try {
            const response = await fetch(event.request);
            if (response.ok || response.type === 'opaque') {
                await cache.put(event.request, response.clone());
            }
            return response;
        } catch (error) {
            const cachedResponse = await caches.match(event.request);
            if (cachedResponse) {
                return cachedResponse;
            }

            if (event.request.mode === 'navigate') {
                return (await caches.match('/portal')) || (await caches.match('/'));
            }

            throw error;
        }
    })());
});
