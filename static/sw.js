/**
 * AgriCopilot Service Worker
 * Implements a Cache-First strategy for static assets and
 * Network-First for API calls with fallback to cache.
 * Designed for low-connectivity agricultural field environments.
 */

const CACHE_NAME = 'agricopilot-v1.2';
const STATIC_CACHE = 'agricopilot-static-v1.2';
const API_CACHE = 'agricopilot-api-v1.2';

// Assets to cache on install (App Shell)
const PRECACHE_ASSETS = [
  '/',
  '/history',
  '/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  // External CDN assets
  'https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;600&display=swap',
  'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css',
  'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js',
];

// ── Install: Pre-cache App Shell ───────────────────────────────────────────
self.addEventListener('install', (event) => {
  console.log('[AgriCopilot SW] Installing v1.2...');
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => {
        console.log('[AgriCopilot SW] Pre-caching app shell...');
        // Cache assets individually so one failure doesn't break all
        return Promise.allSettled(
          PRECACHE_ASSETS.map(url =>
            cache.add(url).catch(err => {
              console.warn(`[SW] Failed to cache: ${url}`, err.message);
            })
          )
        );
      })
      .then(() => {
        console.log('[AgriCopilot SW] App shell cached. Skipping waiting.');
        return self.skipWaiting();
      })
  );
});

// ── Activate: Clean Old Caches ─────────────────────────────────────────────
self.addEventListener('activate', (event) => {
  console.log('[AgriCopilot SW] Activating...');
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter(name =>
            name.startsWith('agricopilot-') &&
            name !== STATIC_CACHE &&
            name !== API_CACHE
          )
          .map(name => {
            console.log(`[SW] Removing old cache: ${name}`);
            return caches.delete(name);
          })
      );
    }).then(() => {
      console.log('[AgriCopilot SW] Activated. Taking control of all clients.');
      return self.clients.claim();
    })
  );
});

// ── Fetch: Smart Routing Strategy ─────────────────────────────────────────
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Never intercept POST requests (file uploads, analysis)
  if (event.request.method !== 'GET') {
    return;
  }

  // API endpoints: Network-First, fall back to cache
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirstStrategy(event.request, API_CACHE, 5000));
    return;
  }

  // PDF downloads: Network only (always fresh)
  if (url.pathname.startsWith('/report/')) {
    event.respondWith(fetch(event.request));
    return;
  }

  // App pages: Network-First with offline fallback
  if (url.origin === location.origin) {
    event.respondWith(networkFirstStrategy(event.request, STATIC_CACHE, 8000));
    return;
  }

  // External resources (CDN, fonts, tiles): Cache-First
  event.respondWith(cacheFirstStrategy(event.request));
});

// ── Strategy: Cache-First ──────────────────────────────────────────────────
async function cacheFirstStrategy(request) {
  const cache = await caches.open(STATIC_CACHE);
  const cached = await cache.match(request);

  if (cached) {
    // Refresh cache in background
    fetchAndCache(request, cache).catch(() => {});
    return cached;
  }

  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      await cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (err) {
    console.warn('[SW] Network failed for cache-first:', request.url, err.message);
    return new Response(
      JSON.stringify({ error: 'Offline. No cached version available.' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }
    );
  }
}

// ── Strategy: Network-First ─────────────────────────────────────────────────
async function networkFirstStrategy(request, cacheName, timeoutMs) {
  const cache = await caches.open(cacheName);

  try {
    // Race network against timeout
    const networkResponse = await Promise.race([
      fetch(request.clone()),
      timeout(timeoutMs),
    ]);

    if (networkResponse.ok) {
      await cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (err) {
    // Network failed/timed out — fall back to cache
    const cached = await cache.match(request);
    if (cached) {
      console.log('[SW] Network failed, serving from cache:', request.url);
      return cached;
    }

    // Return offline page for HTML requests
    if (request.headers.get('Accept')?.includes('text/html')) {
      return offlinePage();
    }

    return new Response(
      JSON.stringify({
        error: 'You appear to be offline. Scan history unavailable.',
        offline: true,
      }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }
    );
  }
}

// ── Helpers ────────────────────────────────────────────────────────────────
function timeout(ms) {
  return new Promise((_, reject) =>
    setTimeout(() => reject(new Error(`Network timeout after ${ms}ms`)), ms)
  );
}

async function fetchAndCache(request, cache) {
  const response = await fetch(request);
  if (response.ok) {
    await cache.put(request, response.clone());
  }
  return response;
}

function offlinePage() {
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgriCopilot — Offline</title>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #fff; color: #0A0A0A;
      display: flex; align-items: center; justify-content: center;
      min-height: 100vh; margin: 0; padding: 20px;
      text-align: center;
    }
    .icon { font-size: 4rem; margin-bottom: 20px; }
    h1 { font-size: 1.6rem; color: #1A7A42; margin-bottom: 12px; }
    p { font-size: 1rem; color: #555; max-width: 320px; line-height: 1.6; }
    .retry-btn {
      margin-top: 24px;
      padding: 12px 28px;
      background: #1A7A42; color: #fff;
      border: none; border-radius: 8px;
      font-size: 1rem; font-weight: 700;
      cursor: pointer;
    }
  </style>
</head>
<body>
  <div>
    <div class="icon">📵</div>
    <h1>You're Offline</h1>
    <p>AgriCopilot needs an internet connection to analyze crops and fetch weather data. Please connect to a network and try again.</p>
    <button class="retry-btn" onclick="window.location.reload()">🔄 Retry</button>
  </div>
</body>
</html>`;

  return new Response(html, {
    status: 200,
    headers: { 'Content-Type': 'text/html; charset=utf-8' },
  });
}