// sw.js - Service Worker for Bilingual Reader Offline Caching

const CORE_CACHE_NAME = 'bilingual-reader-core-v20';
const BOOK_CACHE_NAME = 'bilingual-reader-books';

// Core assets to pre-cache on install
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/favicon.png',
  '/app.js',
  '/books.js',
  '/config.js',
  '/reader.css',
  '/libs/preact.mjs',
  '/libs/hooks.mjs',
  '/libs/htm.mjs'
];

// Install event: Pre-cache core application shell
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CORE_CACHE_NAME).then((cache) => {
      return Promise.allSettled(
        STATIC_ASSETS.map(asset => 
          cache.add(asset).catch(err => console.warn(`[Service Worker] Pre-cache failed for ${asset}:`, err))
        )
      );
    })
  );
  self.skipWaiting();
});

// Activate event: Clean up old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CORE_CACHE_NAME && cacheName !== BOOK_CACHE_NAME) {
            console.log(`[Service Worker] Deleting old cache: ${cacheName}`);
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
  self.clients.claim();
});

// Fetch event: Intercept network requests and cache strategically
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Intercept only GET requests
  if (event.request.method !== 'GET') {
    return;
  }

  // Exclude AI API proxy endpoint from caching
  if (url.pathname.startsWith('/api/chat') || url.pathname.startsWith('/api/')) {
    return;
  }

  const isBookResource = url.pathname.includes('/books/');
  const isSameOrigin = url.origin === self.location.origin;
  const isCdnResource = url.origin.includes('esm.sh') || url.origin.includes('fonts.googleapis.com') || url.origin.includes('fonts.gstatic.com');

  if (!isSameOrigin && !isCdnResource) {
    return;
  }

  // 1. Cache-First Strategy for Book Resources (HTML pages, book assets)
  if (isBookResource) {
    event.respondWith(
      caches.match(event.request).then((cachedResponse) => {
        if (cachedResponse) {
          return cachedResponse;
        }
        // If not in cache, fetch from network and dynamically cache it
        return fetch(event.request).then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const responseToCache = networkResponse.clone();
            caches.open(BOOK_CACHE_NAME).then((cache) => {
              cache.put(event.request, responseToCache);
            });
          }
          return networkResponse;
        }).catch((err) => {
          console.warn(`[Service Worker] Fetch failed for book resource: ${url.pathname}`, err);
          return new Response('Offline Page Content (Not Cached)', { status: 404, statusText: 'Not Found' });
        });
      })
    );
    return;
  }

  // 2. Stale-While-Revalidate for Application Shell & CDN scripts/fonts
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      const fetchPromise = fetch(event.request).then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200) {
          const responseToCache = networkResponse.clone();
          caches.open(CORE_CACHE_NAME).then((cache) => {
            cache.put(event.request, responseToCache);
          });
        }
        return networkResponse;
      }).catch((err) => {
        // Silent catch for background fetches when offline
        if (cachedResponse) {
          return cachedResponse;
        }
        return new Response('Network error occurred. Please check your connection.', {
          status: 503,
          statusText: 'Service Unavailable',
          headers: { 'Content-Type': 'text/plain' }
        });
      });

      // Return cached response instantly if present, else wait for network
      return cachedResponse || fetchPromise;
    })
  );
});
