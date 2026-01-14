/**
 * Humanitec Service Worker
 * Обеспечивает офлайн-работу, кэширование и push-уведомления
 */

const CACHE_NAME = 'humanitec-v1';
const STATIC_CACHE_NAME = 'humanitec-static-v1';
const DYNAMIC_CACHE_NAME = 'humanitec-dynamic-v1';

// Статические ресурсы для предварительного кэширования
const STATIC_ASSETS = [
  '/',
  '/offline.html',
  '/static/core/assets/css/tokens.css',
  '/static/core/assets/css/reset.css',
  '/static/core/assets/js/lit/lit.min.js',
  '/static/core/assets/js/zustand-bundle.js',
  '/static/core/pwa/icons/icon-192x192.png',
  '/static/core/pwa/icons/icon-512x512.png',
  '/static/frontend/styles/landing.css'
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

  // API запросы - Network First
  if (url.pathname.startsWith('/api/') || 
      url.pathname.includes('/api/')) {
    event.respondWith(networkFirst(request));
    return;
  }

  // Статика - Cache First
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(cacheFirst(request));
    return;
  }

  // HTML страницы - Network First с offline fallback
  if (request.headers.get('accept')?.includes('text/html')) {
    event.respondWith(networkFirstWithOffline(request));
    return;
  }

  // Остальное - Network First
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
    if (response.ok) {
      const cache = await caches.open(STATIC_CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    console.error('[SW] Cache first failed:', error);
    throw error;
  }
}

/**
 * Network First стратегия
 * Сначала пытаемся загрузить из сети, если не получается - из кэша
 */
async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(DYNAMIC_CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    const cached = await caches.match(request);
    if (cached) {
      return cached;
    }
    throw error;
  }
}

/**
 * Network First с offline fallback для HTML страниц
 */
async function networkFirstWithOffline(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(DYNAMIC_CACHE_NAME);
      cache.put(request, response.clone());
    }
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
    
    throw error;
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
    self.registration.showNotification(data.title || 'Humanitec', options)
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
  
  if (event.data === 'skipWaiting') {
    self.skipWaiting();
  }
  
  if (event.data?.type === 'CACHE_URLS') {
    event.waitUntil(
      caches.open(DYNAMIC_CACHE_NAME)
        .then((cache) => cache.addAll(event.data.urls))
    );
  }
});
