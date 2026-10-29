import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';

import { App } from './app';
import { routes } from './app.routes';
import { WEB_SOCKET_FACTORY, WS_URL } from './chat/chat-ws.tokens';
import { MockWebSocket } from './chat/mock-web-socket';

describe('App', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideRouter(routes),
        { provide: WS_URL, useValue: 'ws://test.example:8000/ws' },
        {
          provide: WEB_SOCKET_FACTORY,
          useValue: (url: string) => new MockWebSocket(url) as unknown as WebSocket,
        },
      ],
    }).compileComponents();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(App);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should render the Russian chat shell, not the CLI welcome', async () => {
    const fixture = TestBed.createComponent(App);
    const router = TestBed.inject(Router);
    await router.navigateByUrl('/');
    await fixture.whenStable();
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('app-chat-shell')).toBeTruthy();
    expect(compiled.textContent).toContain('Lingua AI');
    expect(compiled.textContent).toContain('Отправить');
    expect(compiled.textContent).not.toContain('Congratulations');
    expect(compiled.textContent).not.toContain('Hello, web');
  });
});
