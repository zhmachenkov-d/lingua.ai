import { mapCtaIds } from './cta-labels';

describe('mapCtaIds', () => {
  it('maps tutor / vocabulary / review to Tutor | Vocabulary | Review', () => {
    expect(mapCtaIds(['tutor', 'vocabulary', 'review'])).toEqual([
      { id: 'tutor', label: 'Tutor' },
      { id: 'vocabulary', label: 'Vocabulary' },
      { id: 'review', label: 'Review' },
    ]);
  });

  it('drops unknown ids', () => {
    expect(mapCtaIds(['tutor', 'unknown', 'review'])).toEqual([
      { id: 'tutor', label: 'Tutor' },
      { id: 'review', label: 'Review' },
    ]);
  });
});
