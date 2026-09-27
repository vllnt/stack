# Changelog

## Unreleased

## 0.1.0-canary.5

- Rename the marketplace from `vllnt-stack` to `vllnt` for all hosts, so installs read `vstack@vllnt`. Existing installs must remove the `vllnt-stack` marketplace and add `vllnt/stack` again.

## 0.1.0-canary.4

- Use the vllnt logo as the Claude plugin icon: `assets/vllnt-logo.png` is wrapped by the generator into `.claude-plugin/icon.svg`.

- Remove distribution version numbers from the README so routine version bumps need no README edits; `VERSION` and this changelog remain the version records.

- Record the `v0.1.0-canary.3` GitHub prerelease.

- Refresh README and AGENTS guidance: vllnt introduction, current canary status and install evidence, directory submission state, and asset ownership.

## 0.1.0-canary.3

- Describe Vstack as part of the vllnt universe and set the Claude plugin homepage to https://vllnt.com.

## 0.1.0-canary.2

- Add a Claude plugin icon owned by this repository (`assets/claude-icon.svg`) and a clearer shared plugin and Claude marketplace description, both through the generator.

- Record Claude Code installation of `0.1.0-canary.1` from the public GitHub marketplace source; skill invocation behavior remains unverified.

## 0.1.0-canary.1

- Publish the first canary for Claude Code verification; stable `0.1.0` follows once Claude Code, Codex, and Cursor are verified. Automatic source updates advance `-canary.N`.

- Add a Claude marketplace description and Claude plugin homepage, repository, and keywords through the generator; document public Claude Code installation and record isolated local install evidence.

- Accept the user-requested, reviewed Skills update at `472c216f2f043f0add1f83540cc46ea53d20a7cd` as `0.1.0-dev.5`, including collaboration principles and bundled quality-validation guidance. Preserve automatic sensitive-change holds; this update uses a separate protected PR.

- Record independently verified live source-push dispatch, automatic protected update/merge, post-merge no-op, and sensitive-change hold receipts; retain explicit host-runtime and scheduled-timer coverage limits.

- Update packaged skills from `ffb5025dfa9f25fab868a4f12f9fb661ac7bfb87` to `14b8ad3dbba8ea820478d3ea2d379c2863de56d9` (0.1.0-dev.4).

- Update packaged skills from `baa90d516fe19e55128e6df8691bb619e1d4f822` to `ffb5025dfa9f25fab868a4f12f9fb661ac7bfb87` (0.1.0-dev.3).

- Wait within the existing bounded CI loop for a known previous PR head to propagate after a leased update; retain immediate stops for manual holds and unexpected PR/branch identities, with no repeated writes.

- Fix generated update-PR help text accidentally containing the manual-hold marker; exercise the actual posted body against the unchanged hold guard, preserving intentional operator holds.

- Accept the independently reviewed source-notification baseline at `baa90d516fe19e55128e6df8691bb619e1d4f822` after the live updater correctly held its workflow/script changes; regenerate distribution `0.1.0-dev.2` through a protected PR.

- Read CI checks with the workflow's built-in token instead of requiring an unavailable Checks permission on the operator's fine-grained personal token; keep both credentials out of candidate tests.

- Make retired updater holds recoverable only through exact closed-PR/head acknowledgements reviewed on main; preserve unknown branches and live holds, with daily fallback scheduling and regression coverage.

- Add a trusted-main, dispatch/scheduled/manual skills updater with full Git classification, deterministic candidate reconstruction, preserved human holds, leased PR updates, exact-head protected merging, and offline regression tests. Hosted activation and cross-repository end-to-end evidence remain pending.

- Initialize Vstack distribution for Claude Code, Codex, and Cursor from a pinned `vllnt/skills` commit, with self-contained packages, provenance, a generated Cursor principles rule, and tested maintenance tooling.
