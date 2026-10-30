# Lingua test quality (persistent facts)

- Tests you add or change must include real assertions: pytest `assert` / `pytest.raises` / mock `assert_*`, or Vitest `expect(...)`. Do not ship vacuous tests (`assert True`, empty bodies, sole `expect(true).toBe(true)`).
- Vacuous or assertion-less tests in the diff fail the hard `assertion-guard` layer of `python scripts/quality_gate.py --base origin/main` (factory verify + CI `quality-ast`).
- For pure **Always** invariants in plan Boundaries, prefer Hypothesis `@given` in `apps/api` or fast-check (`fc.assert` / `fc.property`) in `apps/web`.
- Factory land runs `python scripts/quality_gate.py --base origin/main` via `[verify].commands` when policy is initialized from the template.
