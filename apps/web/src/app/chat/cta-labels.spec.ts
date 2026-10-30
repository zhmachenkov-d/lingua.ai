import { CTA_INTENT, mapCtaIds } from './cta-labels';

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
});

describe('CTA_INTENT', () => {
  it('maps agent CTAs to architecture intents', () => {
    expect(CTA_INTENT.tutor).toBe('tutor_unit');
    expect(CTA_INTENT.vocabulary).toBe('vocab_lookup');
    expect(CTA_INTENT.review).toBe('review_daily');
  });
});
