# Lingua verification-gap addendum

Apply these as additional **broken-verification** rules for this repository (on top of the stock verification-gap prompt):

- Vacuous asserts (`assert True`, empty test bodies, sole `expect(true).toBe(true)`) are broken verification even when the suite is green — they also fail the mechanical assertion-guard in `quality_gate`.
- When the plan Boundaries state pure **Always** invariants over inputs and the diff only adds Demonstration/example tests (no Hypothesis `@given` / fast-check `fc.property` where a clean pure helper exists), treat that as a regression-gap finding.
