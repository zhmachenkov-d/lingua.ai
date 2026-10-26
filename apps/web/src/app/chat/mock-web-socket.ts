/** Minimal WebSocket stand-in for unit tests. */

type Listener = (event?: Event | MessageEvent | CloseEvent) => void;

export class MockWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  readonly CONNECTING = 0;
  readonly OPEN = 1;
  readonly CLOSING = 2;
  readonly CLOSED = 3;

  readyState = MockWebSocket.CONNECTING;
  readonly sent: string[] = [];
  url: string;

  private readonly listeners = new Map<string, Set<Listener>>();

  constructor(url: string) {
    this.url = url;
  }

  addEventListener(type: string, listener: Listener): void {
    let set = this.listeners.get(type);
    if (!set) {
      set = new Set();
      this.listeners.set(type, set);
    }
    set.add(listener);
  }

  removeEventListener(type: string, listener: Listener): void {
    this.listeners.get(type)?.delete(listener);
  }

  send(data: string): void {
    if (this.readyState !== MockWebSocket.OPEN) {
      throw new Error('InvalidStateError');
    }
    this.sent.push(data);
  }

  close(): void {
    if (this.readyState >= MockWebSocket.CLOSING) {
      return;
    }
    this.readyState = MockWebSocket.CLOSED;
    this.emit('close', new CloseEvent('close'));
  }

  /** Test helper: mark open and fire `open`. */
  simulateOpen(): void {
    this.readyState = MockWebSocket.OPEN;
    this.emit('open', new Event('open'));
  }

  /** Test helper: deliver a server frame. Objects are JSON-encoded; strings are raw wire data. */
  simulateMessage(payload: unknown): void {
    const data = typeof payload === 'string' ? payload : JSON.stringify(payload);
    this.emit('message', new MessageEvent('message', { data }));
  }

  /** Test helper: abnormal close (connect fail / 409 / mid-turn death). */
  simulateAbnormalClose(): void {
    this.readyState = MockWebSocket.CLOSED;
    this.emit('error', new Event('error'));
    this.emit('close', new CloseEvent('close', { wasClean: false, code: 1006 }));
  }

  private emit(type: string, event: Event): void {
    const set = this.listeners.get(type);
    if (!set) {
      return;
    }
    for (const listener of set) {
      listener(event);
    }
  }
}
