// O service worker do Solis (26/11/2026): só os avisos no celular (Web Push,
// backend/solis/push.py). Não guarda nada em cache: a tela vem sempre do servidor.
//
// O aviso chega cifrado do servidor; o navegador decifra e entrega aqui o JSON
// {titulo, texto, tag}. Mesma tag = substitui o aviso anterior (um site que caiu e
// voltou não empilha dois).

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (evento) => evento.waitUntil(self.clients.claim()));

self.addEventListener('push', (evento) => {
  let aviso = {};
  try {
    aviso = evento.data ? evento.data.json() : {};
  } catch {
    aviso = { texto: evento.data ? evento.data.text() : '' };
  }
  evento.waitUntil(
    self.registration.showNotification(aviso.titulo || 'Solis', {
      body: aviso.texto || '',
      tag: aviso.tag || undefined,
      icon: '/icone-192.png',
      badge: '/icone-192.png',
      lang: 'pt-BR',
    }),
  );
});

// Tocar no aviso abre o Solis (ou traz pra frente a aba que já está aberta).
self.addEventListener('notificationclick', (evento) => {
  evento.notification.close();
  evento.waitUntil(
    (async () => {
      const abertas = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
      for (const aba of abertas) if ('focus' in aba) return aba.focus();
      return self.clients.openWindow('/');
    })(),
  );
});
