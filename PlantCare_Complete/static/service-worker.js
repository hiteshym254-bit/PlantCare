
const CACHE_NAME = "plantcare-shell-v2";

const APP_SHELL = [
  "/login",
  "/static/style.css",
  "/static/app.js",
  "/static/leaf.svg",
  "/static/plantcare-icon.png?v=20261025",
  "/manifest.webmanifest"
];

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(APP_SHELL))
      .catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", event => {
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

// Keep existing static-file caching behavior.
self.addEventListener("fetch", event => {
  const request = event.request;
  const url = new URL(request.url);

  if (
    request.method !== "GET" ||
    url.origin !== self.location.origin
  ) {
    return;
  }

  if (
    url.pathname.startsWith("/static/") ||
    url.pathname === "/manifest.webmanifest"
  ) {
    event.respondWith(
      caches.match(request).then(cached =>
        cached ||
        fetch(request).then(response => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE_NAME)
              .then(cache => cache.put(request, copy));
          }
          return response;
        })
      )
    );
  }
});

// Receive real push messages from the server.
self.addEventListener("push", event => {
  let data = {};

  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = {
      body: event.data ? event.data.text() : "Check your plants today."
    };
  }

  const title = data.title || "PlantCare 🌿";

  const options = {
    body: data.body || "One of your plants may need attention.",
    icon: "/static/plantcare-icon.png?v=20261025",
    badge: "/static/leaf.svg",
    tag: data.tag || "plantcare-reminder",
    data: {
      url: data.url || "/dashboard"
    }
  };

  event.waitUntil(
    self.registration.showNotification(title, options)
  );
});

// Open PlantCare when the user taps a notification.
self.addEventListener("notificationclick", event => {
  event.notification.close();

  const targetUrl = new URL(
    event.notification.data?.url || "/dashboard",
    self.location.origin
  );

  if (targetUrl.origin !== self.location.origin) {
    return;
  }

  event.waitUntil(
    clients.matchAll({
      type: "window",
      includeUncontrolled: true
    }).then(windowClients => {
      for (const client of windowClients) {
        if ("focus" in client) {
          return client.navigate(targetUrl.href)
            .then(() => client.focus());
        }
      }

      return clients.openWindow(targetUrl.href);
    })
  );
});
