# Changelog

## Unreleased

- Accept the independently reviewed source-notification baseline at `baa90d516fe19e55128e6df8691bb619e1d4f822` after the live updater correctly held its workflow/script changes; regenerate distribution `0.1.0-dev.2` through a protected PR.

- Read CI checks with the workflow's built-in token instead of requiring an unavailable Checks permission on the operator's fine-grained personal token; keep both credentials out of candidate tests.

- Make retired updater holds recoverable only through exact closed-PR/head acknowledgements reviewed on main; preserve unknown branches and live holds, with daily fallback scheduling and regression coverage.

- Add a trusted-main, dispatch/scheduled/manual skills updater with full Git classification, deterministic candidate reconstruction, preserved human holds, leased PR updates, exact-head protected merging, and offline regression tests. Hosted activation and cross-repository end-to-end evidence remain pending.

- Initialize Vstack distribution for Claude Code, Codex, and Cursor from a pinned `vllnt/skills` commit, with self-contained packages, provenance, a generated Cursor principles rule, and tested maintenance tooling.
