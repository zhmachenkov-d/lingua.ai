import type { CtaChip, CtaId } from './chat.types';

const CTA_LABELS: Record<CtaId, string> = {
  tutor: 'Tutor',
  vocabulary: 'Vocabulary',
  review: 'Review',
};

const KNOWN_IDS = new Set<string>(Object.keys(CTA_LABELS));

/** Map server `ctas` ids → display chips; unknown ids are dropped. */
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
