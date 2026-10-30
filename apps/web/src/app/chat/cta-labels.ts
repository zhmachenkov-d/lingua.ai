import type { CtaChip, CtaId } from './chat.types';

const CTA_LABELS: Record<CtaId, string> = {
  tutor: 'Tutor',
  vocabulary: 'Vocabulary',
  review: 'Review',
  cefr: 'Указать CEFR',
  confirm_unit: 'Сменить',
  decline_unit: 'Оставить',
};

/** CTA chip id → turn intent token (cefr navigates; not classified). */
export const CTA_INTENT: Record<Exclude<CtaId, 'cefr'>, string> = {
  tutor: 'tutor_unit',
  vocabulary: 'vocab_lookup',
  review: 'review_daily',
  confirm_unit: 'confirm_unit',
  decline_unit: 'decline_unit',
};

const KNOWN_IDS = new Set<string>(Object.keys(CTA_LABELS));

/** Map server `ctas` ids → display chips; unknown ids are dropped (shell errors if all drop). */
export function mapCtaIds(ids: readonly string[]): CtaChip[] {
  const chips: CtaChip[] = [];
  for (const id of ids) {
    if (!KNOWN_IDS.has(id)) {
      continue;
    }
    const ctaId = id as CtaId;
    chips.push({ id: ctaId, label: CTA_LABELS[ctaId] });
  }
  return chips;
}
