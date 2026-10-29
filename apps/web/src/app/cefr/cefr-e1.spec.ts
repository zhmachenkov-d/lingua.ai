import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';

import { CefrE1 } from './cefr-e1';

describe('CefrE1', () => {
  let fixture: ComponentFixture<CefrE1>;
  let httpMock: HttpTestingController;
  let router: Router;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CefrE1],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
    fixture = TestBed.createComponent(CefrE1);
    fixture.detectChanges();
  });

  afterEach(() => {
    httpMock.verify();
  });

  async function flushInitGet(body: Record<string, string> = {}): Promise<void> {
    const get = httpMock.expectOne('/api/profile/cefr');
    expect(get.request.method).toBe('GET');
    get.flush(body);
    await fixture.whenStable();
    fixture.detectChanges();
  }

  it('GETs existing overall on init and prefills the select', async () => {
    await flushInitGet({ overall: 'B1' });

    expect(fixture.componentInstance['overall']()).toBe('B1');
    const select = fixture.nativeElement.querySelector('#e1-overall') as HTMLSelectElement;
    expect(select.value).toBe('B1');
  });

  it('PUTs overall CEFR then returns to chat', async () => {
    await flushInitGet({});
    const navigateSpy = vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);
    const component = fixture.componentInstance;
    component['overall'].set('A2');
    fixture.detectChanges();

    const submitPromise = component['onSubmit'](new Event('submit'));
    const req = httpMock.expectOne('/api/profile/cefr');
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toEqual({ overall: 'A2' });
    req.flush('', { status: 204, statusText: 'No Content' });
    await submitPromise;

    expect(navigateSpy).toHaveBeenCalledWith('/');
  });

  it('shows error when PUT fails', async () => {
    await flushInitGet({});
    const component = fixture.componentInstance;
    component['overall'].set('B1');
    const submitPromise = component['onSubmit'](new Event('submit'));
    httpMock.expectOne('/api/profile/cefr').flush('fail', {
      status: 500,
      statusText: 'Server Error',
    });
    await submitPromise;
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Не удалось сохранить уровень');
  });
});
