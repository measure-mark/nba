# Coding Preferences

## Clarity

- Write code that is simple to understand. A reader should not need to hold much
  in their head to follow it.
- Fewer lines are better than more. Prefer the shorter version when both are
  equally clear.

## Abstraction

- Avoid unnecessary abstraction. Abstraction should exist only where it adds
  clear and present value — not for hypothetical future needs.
- Object-oriented programming is the preferred form of abstraction.
- Use Gang of Four patterns where they genuinely fit the problem. Name them when
  you use them.

## Loops and comprehensions

- Prefer list comprehensions to `for` loops.
- Never nest a comprehension more than 2 levels deep. If more depth is needed,
  break it into a series of generators.

## Tabular data

- Use pandas and numpy for tabular data manipulation. Express work as vectorized
  operations, boolean masks, `groupby`, `merge`, and `assign` rather than `for`
  loops and `if` statements over rows.
- Avoid `iterrows`, `itertuples`, and row-wise `apply` unless there is no
  vectorized equivalent — and say why when that happens.

## Tests

- Every unit test must be tied to one of:
  - a business rule,
  - a bug (regression test),
  - a contract or design decision that needs enforcing.
- Do not write tests for the sake of coverage. Tests are written with purpose.
- If a test's purpose isn't obvious from its name, say it in a one-line comment
  or docstring.
