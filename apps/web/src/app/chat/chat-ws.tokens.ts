import { InjectionToken } from '@angular/core';

/** Default: same-origin `/ws` with `wss` when the page is HTTPS — override in tests. */
export function defaultWsUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws`;
}

export const WS_URL = new InjectionToken<string>('WS_URL', {
  providedIn: 'root',
  factory: defaultWsUrl,
});

export type WebSocketFactory = (url: string) => WebSocket;

export const WEB_SOCKET_FACTORY = new InjectionToken<WebSocketFactory>('WEB_SOCKET_FACTORY', {
  providedIn: 'root',
  factory: () => (url: string) => new WebSocket(url),
});
