/**
 * Service Worker Humanitec
 * Обеспечивает офлайн-работу, кэширование и push-уведомления
 */

const CACHE_SCHEMA_VERSION = 'v6';
const STATIC_CACHE_NAME = `humanitec-static-${CACHE_SCHEMA_VERSION}`;
const DYNAMIC_CACHE_NAME = `humanitec-dynamic-${CACHE_SCHEMA_VERSION}`;
const METADATA_CACHE_NAME = 'humanitec-metadata-v1';
const DEPLOYMENT_VERSION_CACHE_KEY = '/__humanitec_pwa/deployment-version';
const DEPLOYMENT_CHECK_MIN_INTERVAL_MS = 30_000;
let deploymentCheckInFlight = null;
let lastDeploymentCheckAt = 0;

// Статические ресурсы для предварительного кэширования (только пути, доступные на любом сервисе с /static/core)
const STATIC_ASSETS = [
  '/',
  '/offline.html',
  '/static/core/assets/css/tokens.css',
  '/static/core/assets/css/reset.css',
  '/static/core/assets/js/lit/lit.min.js',
  '/static/core/pwa/icons/icon-192x192.png',
  '/static/core/pwa/icons/icon-512x512.png',
];

// Установка: кэшируем offline-минимум, но не блокируем установку при частичной сетевой ошибке.
self.addEventListener('install', (event) => {
  console.log('[SW] Installing...');

  event.waitUntil(
    (async () => {
      try {
        await precacheStaticAssets();
      } catch (error) {
        console.warn('[SW] precache failed:', error);
      }
      await self.skipWaiting();
    })()
  );
});

// Активация: очистка старых кэшей
self.addEventListener('activate', (event) => {
  console.log('[SW] Activating...');

  event.waitUntil(
    (async () => {
      const deletedObsolete = await deleteObsoleteHumanitecCaches();
      const deploymentPurged = await ensureDeploymentFresh({ force: true });
      await self.clients.claim();
      if (deletedObsolete || deploymentPurged) {
        await reloadWindowClients();
      }
    })()
  );
});

function swOrigin() {
  return self.location.origin;
}

function sameOriginRequest(url) {
  return url.origin === swOrigin();
}

function freshRequest(request, cacheMode = 'reload') {
  return new Request(request, { cache: cacheMode });
}

async function fetchFresh(request, cacheMode = 'reload') {
  return fetch(freshRequest(request, cacheMode));
}

async function precacheStaticAssets() {
  const results = await Promise.allSettled(
    STATIC_ASSETS.map(async (assetUrl) => {
      const request = new Request(assetUrl, {
        cache: 'reload',
        credentials: 'same-origin',
      });
      const response = await fetch(request);
      await putInStaticCache(request, response);
    })
  );
  const failed = results.filter((r) => r.status === 'rejected');
  if (failed.length > 0) {
    console.warn('[SW] precache partial failure:', failed.length);
  }
}

async function deleteObsoleteHumanitecCaches() {
  const cacheNames = await caches.keys();
  const allowed = new Set([STATIC_CACHE_NAME, DYNAMIC_CACHE_NAME, METADATA_CACHE_NAME]);
  const toDelete = cacheNames.filter((name) => name.startsWith('humanitec-') && !allowed.has(name));
  await Promise.all(
    toDelete.map((name) => {
      console.log('[SW] Deleting old cache:', name);
      return caches.delete(name);
    })
  );
  return toDelete.length > 0;
}

async function deleteHumanitecContentCaches() {
  const cacheNames = await caches.keys();
  const toDelete = cacheNames.filter((name) => name.startsWith('humanitec-') && name !== METADATA_CACHE_NAME);
  await Promise.all(
    toDelete.map((name) => {
      console.log('[SW] Deleting content cache after deployment change:', name);
      return caches.delete(name);
    })
  );
}

async function readStoredDeploymentVersion() {
  const cache = await caches.open(METADATA_CACHE_NAME);
  const response = await cache.match(DEPLOYMENT_VERSION_CACHE_KEY);
  if (!response) {
    return null;
  }
  try {
    const data = await response.json();
    return typeof data.version === 'string' && data.version.length > 0 ? data.version : null;
  } catch (error) {
    console.warn('[SW] deployment metadata parse failed:', error);
    return null;
  }
}

async function writeStoredDeploymentVersion(version) {
  const cache = await caches.open(METADATA_CACHE_NAME);
  await cache.put(
    DEPLOYMENT_VERSION_CACHE_KEY,
    new Response(JSON.stringify({ version }), {
      headers: {
        'Content-Type': 'application/json',
        'Cache-Control': 'no-store',
      },
    })
  );
}

async function fetchServerDeploymentVersion() {
  const response = await fetch(new Request('/health', {
    cache: 'no-store',
    credentials: 'same-origin',
    headers: { 'Cache-Control': 'no-cache' },
  }));
  if (!response.ok) {
    throw new Error(`deployment version check failed: HTTP ${response.status}`);
  }
  const data = await response.json();
  const version = data && (data.deployment_version || data.version);
  return typeof version === 'string' && version.length > 0 ? version : null;
}

async function ensureDeploymentFresh({ force = false } = {}) {
  const now = Date.now();
  if (!force && now - lastDeploymentCheckAt < DEPLOYMENT_CHECK_MIN_INTERVAL_MS) {
    return false;
  }
  if (deploymentCheckInFlight) {
    return deploymentCheckInFlight;
  }
  lastDeploymentCheckAt = now;
  deploymentCheckInFlight = (async () => {
    let serverVersion;
    try {
      serverVersion = await fetchServerDeploymentVersion();
    } catch (error) {
      console.warn('[SW] deployment version check skipped:', error);
      return false;
    }
    if (!serverVersion) {
      return false;
    }
    const storedVersion = await readStoredDeploymentVersion();
    if (storedVersion && storedVersion !== serverVersion) {
      await deleteHumanitecContentCaches();
      await writeStoredDeploymentVersion(serverVersion);
      await notifyWindowClients({
        type: 'humanitec-deployment-updated',
        from: storedVersion,
        to: serverVersion,
      });
      return true;
    }
    if (!storedVersion) {
      await writeStoredDeploymentVersion(serverVersion);
    }
    return false;
  })();
  try {
    return await deploymentCheckInFlight;
  } finally {
    deploymentCheckInFlight = null;
  }
}

async function notifyWindowClients(message) {
  const clientList = await self.clients.matchAll({
    type: 'window',
    includeUncontrolled: true,
  });
  for (const client of clientList) {
    if (client.url && client.url.startsWith(swOrigin())) {
      client.postMessage(message);
    }
  }
}

async function reloadWindowClients() {
  const clientList = await self.clients.matchAll({
    type: 'window',
    includeUncontrolled: true,
  });
  await Promise.all(
    clientList.map(async (client) => {
      if (!client.url || !client.url.startsWith(swOrigin())) {
        return;
      }
      if (typeof client.navigate === 'function') {
        try {
          await client.navigate(client.url);
          return;
        } catch (error) {
          console.warn('[SW] client.navigate failed:', client.url, error);
        }
      }
      client.postMessage({ type: 'humanitec-deployment-reload-requested' });
    })
  );
}

/**
 * Cache Storage принимает только «полные» ответы: 206 (Range) и прочие неполные ответы дают TypeError при put.
 */
function canPutInCache(response) {
  if (!response || !response.ok) {
    return false;
  }
  if (response.status !== 200) {
    return false;
  }
  if (response.headers.get('Content-Range')) {
    return false;
  }
  return true;
}

async function putInDynamicCache(request, response) {
  if (!canPutInCache(response)) {
    return;
  }
  const cache = await caches.open(DYNAMIC_CACHE_NAME);
  try {
    await cache.put(request, response.clone());
  } catch (err) {
    console.warn('[SW] cache.put пропущен:', request.url, err);
  }
}

async function putInStaticCache(request, response) {
  if (!canPutInCache(response)) {
    return;
  }
  const cache = await caches.open(STATIC_CACHE_NAME);
  try {
    await cache.put(request, response.clone());
  } catch (err) {
    console.warn('[SW] cache.put пропущен:', request.url, err);
  }
}

// Fetch: стратегии кэширования
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Пропускаем не-GET запросы
  if (request.method !== 'GET') {
    return;
  }

  // Пропускаем WebSocket
  if (url.pathname.includes('/ws/')) {
    return;
  }

  // Пропускаем chrome-extension и другие схемы
  if (!url.protocol.startsWith('http')) {
    return;
  }

  // Только свой origin — иначе fetch из SW падает (CORS / чужой хост) и даёт Uncaught в promise
  if (!sameOriginRequest(url)) {
    return;
  }

  // Сессия и токены: никогда не кэшируем и не отдаём из Cache Storage (иначе устаревший /me ломает auth)
  if (url.pathname.includes('/api/auth/')) {
    event.respondWith(
      fetch(request).catch((err) => {
        console.error('[SW] auth fetch:', err);
        return new Response('', { status: 503, statusText: 'Service Unavailable' });
      })
    );
    return;
  }

  // Версия деплоя и health: только сеть, без Cache Storage (иначе клиент не видит новый релиз)
  if (url.pathname === '/health' || url.pathname.endsWith('/health')) {
    event.respondWith(
      fetchFresh(request, 'no-store').catch((err) => {
        console.error('[SW] health fetch:', err);
        return new Response('', { status: 503, statusText: 'Service Unavailable' });
      })
    );
    return;
  }

  // API запросы - сначала сеть
  if (url.pathname.startsWith('/api/') || 
      url.pathname.includes('/api/')) {
    event.respondWith(networkFirst(request));
    return;
  }

  // Изменяемая ESM/CSS/HTML-статика: сеть первая, Cache Storage только как offline fallback.
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(networkFirstStatic(request));
    return;
  }

  // HTML страницы - сначала сеть с offline-резервом
  if (request.headers.get('accept')?.includes('text/html')) {
    event.respondWith(networkFirstWithOffline(request));
    return;
  }

  // Остальное - сначала сеть
  event.respondWith(networkFirst(request));
});

async function networkFirstStatic(request) {
  await ensureDeploymentFresh();
  try {
    const response = await fetchFresh(request, 'reload');
    await putInStaticCache(request, response);
    return response;
  } catch (error) {
    const cached = await caches.match(request);
    if (cached) {
      return cached;
    }
    console.warn('[SW] networkFirstStatic: сеть недоступна, кэша нет', request.url, error);
    return new Response('', { status: 504, statusText: 'Gateway Timeout' });
  }
}

/**
 * стратегия «сначала сеть»
 * Сначала пытаемся загрузить из сети, если не получается - из кэша
 */
async function networkFirst(request) {
  try {
    const response = await fetchFresh(request, 'reload');
    await putInDynamicCache(request, response);
    return response;
  } catch (error) {
    const cached = await caches.match(request);
    if (cached) {
      return cached;
    }
    console.warn('[SW] networkFirst: сеть недоступна, кэша нет', request.url);
    return new Response('', { status: 503, statusText: 'Service Unavailable' });
  }
}

/**
 * сначала сеть с offline-резервом для HTML страниц
 */
async function networkFirstWithOffline(request) {
  await ensureDeploymentFresh({ force: true });
  try {
    const response = await fetchFresh(request, 'reload');
    await putInDynamicCache(request, response);
    return response;
  } catch (error) {
    const cached = await caches.match(request);
    if (cached) {
      return cached;
    }
    
    // Возвращаем offline страницу
    const offlinePage = await caches.match('/offline.html');
    if (offlinePage) {
      return offlinePage;
    }

    console.warn('[SW] networkFirstWithOffline: нет сети и offline.html', request.url);
    return new Response('', { status: 503, statusText: 'Service Unavailable' });
  }
}

// Push-уведомления
self.addEventListener('push', (event) => {
  console.log('[SW] Push received');
  
  if (!event.data) {
    console.log('[SW] Push event but no data');
    return;
  }

  let data;
  try {
    data = event.data.json();
  } catch (e) {
    data = {
      title: 'Humanitec',
      message: event.data.text()
    };
  }

  const options = {
    body: data.message || data.body || '',
    icon: '/static/core/pwa/icons/icon-192x192.png',
    badge: '/static/core/pwa/icons/badge-72x72.png',
    vibrate: [100, 50, 100],
    tag: data.tag || data.type || 'notification',
    renotify: true,
    requireInteraction: data.priority === 'urgent' || data.priority === 'high',
    data: {
      url: data.action_url || data.url || '/',
      ...data.data
    },
    actions: data.actions || []
  };

  event.waitUntil(
    (async () => {
      const clientList = await self.clients.matchAll({
        type: 'window',
        includeUncontrolled: true,
      });
      for (const client of clientList) {
        if (client.url && client.url.startsWith(self.location.origin)) {
          client.postMessage({
            type: 'humanitec-web-push',
            payload: {
              title: data.title || 'Humanitec',
              message: data.message || data.body || '',
              tag: data.tag || data.type,
              priority: data.priority,
              url: data.url || data.action_url,
              data: data.data,
            },
          });
        }
      }
      await self.registration.showNotification(data.title || 'Humanitec', options);
    })()
  );
});

// Клик по уведомлению
self.addEventListener('notificationclick', (event) => {
  console.log('[SW] Notification clicked');
  
  event.notification.close();

  const url = event.notification.data?.url || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((clientList) => {
        // Ищем открытое окно приложения
        for (const client of clientList) {
          if (client.url.includes(self.location.origin) && 'focus' in client) {
            client.navigate(url);
            return client.focus();
          }
        }
        // Открываем новое окно
        return clients.openWindow(url);
      })
  );
});

// Закрытие уведомления
self.addEventListener('notificationclose', (event) => {
  console.log('[SW] Notification closed');
});

// Сообщения от клиента
self.addEventListener('message', (event) => {
  console.log('[SW] Message received:', event.data);
  
  if (event.data === 'skipWaiting' || event.data?.type === 'skipWaiting') {
    self.skipWaiting();
  }
  
  if (event.data?.type === 'CACHE_URLS') {
    event.waitUntil(
      caches.open(DYNAMIC_CACHE_NAME)
        .then((cache) => cache.addAll(event.data.urls))
    );
  }
});
