// OPENMOTORS Service Worker v1.0
const CACHE_NAME = 'openmotors-v1';

// Recursos estáticos a cachear para funcionamiento offline básico
const STATIC_ASSETS = [
    '/static/img/favicon.png',
    '/static/img/icon-192.png',
    '/static/img/icon-512.png',
    'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css',
    'https://fonts.googleapis.com/css2?family=DM+Sans:ital,wght@0,300;0,400;0,500;0,600;1,300&family=DM+Mono:wght@400;500&display=swap',
    'https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap',
];

// ── Install ─────────────────────────────
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            return cache.addAll(STATIC_ASSETS).catch(() => {
                // Si algún recurso falla, continuar igual
            });
        })
    );
    self.skipWaiting();
});

// ── Activate ────────────────────────────
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(
                keys
                    .filter(key => key !== CACHE_NAME)
                    .map(key => caches.delete(key))
            )
        )
    );
    self.clients.claim();
});

// ── Fetch — Network first, cache fallback ──
self.addEventListener('fetch', event => {
    const { request } = event;

    // Solo interceptar GET
    if (request.method !== 'GET') return;

    // No interceptar llamadas a la API ni admin
    const url = new URL(request.url);
    if (url.pathname.startsWith('/admin')) return;

    // Recursos estáticos: Cache first
    if (request.destination === 'image' ||
        request.destination === 'style' ||
        request.destination === 'font' ||
        url.pathname.startsWith('/static/')) {

        event.respondWith(
            caches.match(request).then(cached => {
                if (cached) return cached;
                return fetch(request).then(response => {
                    if (response && response.status === 200) {
                        const clone = response.clone();
                        caches.open(CACHE_NAME).then(cache => cache.put(request, clone));
                    }
                    return response;
                }).catch(() => cached);
            })
        );
        return;
    }

    // Páginas HTML: Network first, sin fallback (requiere auth)
    event.respondWith(
        fetch(request).catch(() => caches.match(request))
    );
});