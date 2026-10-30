import * as fc from 'fast-check';

import { CTA_INTENT, mapCtaIds } from './cta-labels';

const KNOWN = ['tutor', 'vocabulary', 'review', 'cefr'] as const;

describe('mapCtaIds', () => {
  it('maps tutor / vocabulary / review / cefr to labels', () => {
    expect(mapCtaIds(['tutor', 'vocabulary', 'review', 'cefr'])).toEqual([
      { id: 'tutor', label: 'Tutor' },
      { id: 'vocabulary', label: 'Vocabulary' },
      { id: 'review', label: 'Review' },
      { id: 'cefr', label: 'Указать CEFR' },
    ]);
  });

  it('drops unknown ids', () => {
    expect(mapCtaIds(['tutor', 'unknown', 'review'])).toEqual([
      { id: 'tutor', label: 'Tutor' },
      { id: 'review', label: 'Review' },
    ]);
  });

  it('keeps only known ids in input order with table labels', () => {
    fc.assert(
      fc.property(fc.array(fc.string()), (ids) => {
        const chips = mapCtaIds(ids);
        const expected = ids.filter((id): id is (typeof KNOWN)[number] =>
          (KNOWN as readonly string[]).includes(id),
        );
        return (
          chips.length === expected.length && chips.every((chip, i) => chip.id === expected[i])
        );
      }),
    );
  });
});

describe('CTA_INTENT', () => {
  it('maps agent CTAs to architecture intents', () => {
    expect(CTA_INTENT.tutor).toBe('tutor_unit');
    expect(CTA_INTENT.vocabulary).toBe('vocab_lookup');
    expect(CTA_INTENT.review).toBe('review_daily');
  });
});
