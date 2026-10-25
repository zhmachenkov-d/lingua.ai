import { InjectionToken } from '@angular/core';

/** Default: `ws://${hostname}:8000/ws` — override in tests. */
export function defaultWsUrl(): string {
  return `ws://${window.location.hostname}:8000/ws`;
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
