import { Component, OnInit, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

const CEFR_LEVELS = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2'] as const;
type CefrLevel = (typeof CEFR_LEVELS)[number];

function isCefrLevel(value: unknown): value is CefrLevel {
  return typeof value === 'string' && (CEFR_LEVELS as readonly string[]).includes(value);
}

@Component({
  selector: 'app-cefr-e1',
  imports: [FormsModule, RouterLink],
  templateUrl: './cefr-e1.html',
  styleUrl: './cefr-e1.css',
})
export class CefrE1 implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);

  protected readonly levels = CEFR_LEVELS;
  protected readonly overall = signal<CefrLevel | ''>('');
  protected readonly saving = signal(false);
  protected readonly error = signal<string | null>(null);

  ngOnInit(): void {
    void this.loadExistingOverall();
  }

  private async loadExistingOverall(): Promise<void> {
    try {
      const map = await firstValueFrom(
        this.http.get<Record<string, string>>('/api/profile/cefr'),
      );
      if (isCefrLevel(map['overall'])) {
        this.overall.set(map['overall']);
      }
    } catch {
      // Prefill is best-effort; leave select empty on load failure.
    }
  }

  protected async onSubmit(event: Event): Promise<void> {
    event.preventDefault();
    const level = this.overall();
    if (!level || this.saving()) {
      return;
    }
    this.saving.set(true);
    this.error.set(null);
    try {
      await firstValueFrom(
        this.http.put('/api/profile/cefr', { overall: level }, { responseType: 'text' }),
      );
      await this.router.navigateByUrl('/');
    } catch {
      this.error.set('Не удалось сохранить уровень. Попробуй ещё раз.');
    } finally {
      this.saving.set(false);
    }
  }
}
