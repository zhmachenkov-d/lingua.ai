import { defaultWsUrl } from './chat-ws.tokens';

describe('defaultWsUrl', () => {
  const originalLocation = window.location;

  afterEach(() => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
    });
  });

  function stubLocation(protocol: string, host: string): void {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { protocol, host },
    });
  }

  it('uses ws and page host/port on http', () => {
    stubLocation('http:', 'localhost:4200');
    expect(defaultWsUrl()).toBe('ws://localhost:4200/ws');
  });

  it('uses wss on https (no hard-coded :8000)', () => {
    stubLocation('https:', 'app.example.com');
    expect(defaultWsUrl()).toBe('wss://app.example.com/ws');
  });
});
