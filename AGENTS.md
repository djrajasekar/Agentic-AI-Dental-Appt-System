# AGENTS.md

Common instructions for AI coding agents working in this repository.
This file is intentionally generic so it can be reused across projects.

## Primary Goals

- Preserve existing behavior unless a change is explicitly requested.
- Prefer small, focused, low-risk changes.
- Keep code readable, maintainable, and easy to review.
- Reuse existing project patterns before introducing new ones.

## Working Style

- Read relevant files before editing.
- Explain assumptions briefly when requirements are unclear.
- Ask before making destructive, broad, or irreversible changes.
- Avoid unrelated refactors during bug fixes or feature work.

## Code Quality

- Favor clarity over cleverness.
- Use descriptive names for functions, classes, and variables.
- Keep functions small and single-purpose when practical.
- Add comments only where the logic is not obvious.
- Do not add unnecessary dependencies.

## Validation

- Run the most relevant checks before claiming completion.
- If tests, linting, or builds cannot be run, say so clearly.
- Report only verified results.

## Testing

- Cover **Happy Path** scenarios for standard successful operations.
- Cover **Edge Cases** such as boundary values, empty inputs, and null values.
- Cover **Error Handling** for invalid inputs and expected failure states.
- Prefer real-behavior tests with isolated test data over heavy mocking.
- When asked for tests, provide complete, runnable test file code.

## Security

- Never commit secrets, tokens, API keys, or credentials.
- Prefer environment variables or secure configuration for sensitive values.
- Avoid logging confidential or personal data.

## Documentation

- Update `README.md` or usage docs when setup, commands, or behavior change.
- Include short examples for new scripts, APIs, or workflows when useful.

## Comments

- Add a 3-line banner comment for each module or major section, with `********` style lines at the top and bottom.
- Write comments so a new person can quickly understand the purpose, flow, and important decisions in the code.
- Add the banner comments for each block.
- Prefer explaining **why** something exists, **what** responsibility it owns, and any important assumptions.
- Keep comments detailed enough to help onboarding, but avoid repeating code that is already obvious.
- Update comments whenever the related code changes so documentation stays trustworthy.
- Use `Step 1`, `Step 2`, and similar labels only when they genuinely help explain a multi-step flow.
- Add clear review or handoff comments when follow-up work is needed.

## Git and Pull Requests

- Keep changes scoped to a single logical purpose.
- Make diffs easy to review.
- Summarize what changed, why it changed, and how it was validated.

## Language Preferences

- Follow the conventions already used in the repository.
- Prefer standard library solutions before adding third-party packages.
- Keep configuration simple and explicit.

## Agent Rule of Thumb

When in doubt: be safe, be minimal, and leave the project clearer than you found it.
