/**
 * Humanitec Service Worker
 * Обеспечивает офлайн-работу, кэширование и push-уведомления
 */

const STATIC_CACHE_NAME = 'humanitec-static-v5';
const DYNAMIC_CACHE_NAME = 'humanitec-dynamic-v5';

// Статические ресурсы для предварительного кэширования (только пути, доступные на любом сервисе с /static/core)
const STATIC_ASSETS = [
  '/',
  '/offline.html',
  '/static/core/assets/css/tokens.css',
  '/static/core/assets/css/reset.css',
  '/static/core/assets/js/lit/lit.min.js',
  '/static/core/assets/js/zustand-bundle.js',
  '/static/core/pwa/icons/icon-192x192.png',
  '/static/core/pwa/icons/icon-512x512.png',
];

// Install: кэшируем статику
self.addEventListener('install', (event) => {
  console.log('[SW] Installing...');
  
  event.waitUntil(
    caches.open(STATIC_CACHE_NAME)
      .then((cache) => {
        console.log('[SW] Caching static assets');
        return cache.addAll(STATIC_ASSETS);
      })
      .then(() => self.skipWaiting())
      .catch((error) => {
        console.error('[SW] Failed to cache static assets:', error);
      })
  );
});

// Activate: очистка старых кэшей
self.addEventListener('activate', (event) => {
  console.log('[SW] Activating...');
  
  event.waitUntil(
    caches.keys()
      .then((cacheNames) => {
        return Promise.all(
          cacheNames
            .filter((name) => {
              return name.startsWith('humanitec-') && 
                     name !== STATIC_CACHE_NAME && 
                     name !== DYNAMIC_CACHE_NAME;
            })
            .map((name) => {
              console.log('[SW] Deleting old cache:', name);
              return caches.delete(name);
            })
        );
      })
      .then(() => self.clients.claim())
  );
});

function swOrigin() {
  return self.location.origin;
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
  if (url.origin !== swOrigin()) {
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
      fetch(request).catch((err) => {
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

  // Статика: отдаём кэш сразу, параллельно обновляем из сети (новый релиз подтягивается без «вечного» stale)
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(staleWhileRevalidateStatic(request));
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

/**
 * Cache First стратегия
 * Сначала ищем в кэше, если нет - загружаем из сети
 */
async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) {
    return cached;
  }
  
  try {
    const response = await fetch(request);
    await putInStaticCache(request, response);
    return response;
  } catch (error) {
    console.error('[SW] Cache first failed:', error);
    return new Response('', { status: 504, statusText: 'Gateway Timeout' });
  }
}

async function staleWhileRevalidateStatic(request) {
  const cached = await caches.match(request);
  const networkPromise = fetch(request)
    .then(async (response) => {
      await putInStaticCache(request, response);
      return response;
    })
    .catch((error) => {
      // Фоновое обновление: при уже отданном из кэша ответе сбой сети не ошибка сценария.
      if (!cached) {
        console.warn('[SW] staleWhileRevalidateStatic: нет кэша и сеть недоступна', request.url, error);
      }
      return null;
    });

  if (cached) {
    void networkPromise;
    return cached;
  }

  const response = await networkPromise;
  if (response) {
    return response;
  }
  return new Response('', { status: 504, statusText: 'Gateway Timeout' });
}

/**
 * стратегия «сначала сеть»
 * Сначала пытаемся загрузить из сети, если не получается - из кэша
 */
async function networkFirst(request) {
  try {
    const response = await fetch(request);
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
  try {
    const response = await fetch(request);
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

// Push Notifications
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
