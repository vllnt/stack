# Vstack

One distribution repository for Vstack plugins for **Claude Code, Codex, and Cursor**: evidence-led engineering workflows to plan, build, review, and ship software with AI agents. Vstack is part of the [vllnt](https://vllnt.com) universe of open, sovereign tools, built for freedom by design.

## Install in Claude Code

The Claude Code plugin is in canary (prerelease versions): installation from GitHub is verified, while skill behavior is still being accepted. Codex and Cursor follow. A stable release follows once all hosts pass. The current version is in [`VERSION`](VERSION); changes are in [`CHANGELOG.md`](CHANGELOG.md).

```text
/plugin marketplace add vllnt/stack
/plugin install vstack@vllnt-stack
```

Then start a new chat and invoke a namespaced skill such as `/vstack:plan-work`. Third-party marketplaces may not auto-update by default; enable auto-update for `vllnt-stack` in `/plugin`, or run `/plugin marketplace update vllnt-stack` to receive new versions.

[`vllnt/skills`](https://github.com/vllnt/skills) owns the portable workflows and principles. This repository pins an upstream commit and builds complete, committed host packages. Installed users need no Python, Git submodule, build step, or runtime source download.

## Ownership and layout

| Path | Owner / purpose |
| --- | --- |
| `upstream.lock.json` | Trusted upstream repository and immutable commit |
| `VERSION` | Shared distribution version |
| `scripts/sync.py` | Standard-library generator and read-only drift check |
| `assets/vllnt-logo.png` | vllnt logo; the generator wraps it as the Claude package's `.claude-plugin/icon.svg` |
| `plugins/claude/` | Generated Claude Code native plugin |
| `plugins/codex/` | Generated portable Agent Plugin for Codex |
| `plugins/cursor/` | Generated Cursor native plugin and principles rule |
| `.claude-plugin/marketplace.json` | Claude Code catalog; selects only its host package |
| `.agents/plugins/marketplace.json` | Codex catalog; selects only its host package |
| `.cursor-plugin/marketplace.json` | Cursor catalog; selects only its host package |

Each catalog exposes a plugin named **`vstack`**, under the marketplace identity **`vllnt-stack`**. Separate package roots avoid relying on precedence between multiple host manifests. Generated copies are distribution artifacts, not additional skill authorship locations.

Each package includes all public `workflows/*/SKILL.md` and `mandatory/*/SKILL.md` folders, their existing reference bundles, the upstream MIT license, and `SOURCE.json`. Repository-local maintenance skills and unrelated installed third-party skills are excluded. The initial pin contains 19 workflows and three principle skills. Workflows are discovered dynamically; changes to the three named mandatory principles intentionally require generator/adapter review before packaging.

## Principles and boundaries

Cursor receives an `alwaysApply` rule generated from the three canonical principle bodies. Claude Code and Codex receive the same principles as discoverable skills, **not an automatic startup adapter**. Their startup loading is a future, separately verified integration; descriptions alone do not enforce it.

The plugin does not install frameworks, activate the optional Vstack stack profile, replace consumer permissions, or install hooks, MCP servers, or custom agents. Guidance is not a security sandbox. Users may need separate tools and credentials for individual workflows, supplied by their consumer projects.

## Local host testing

These are development instructions based on the host documentation. Use a synthetic project and avoid overlapping standalone skill installations. Codex and Cursor steps have not been executed yet.

### Claude Code

From Claude Code, add this checkout as a local marketplace, then install its plugin:

```text
/plugin marketplace add /path/to/stack
/plugin install vstack@vllnt-stack
```

Choose the desired installation scope and reload plugins if prompted. Verify a namespaced invocation such as `/vstack:plan-work` in a new chat.

### Codex

The repository includes `.agents/plugins/marketplace.json`, pointing at the portable plugin under `plugins/codex/`.

```bash
codex plugin marketplace add /path/to/stack
```

Use the supported client plugin browser to install/enable `vstack`; adding a marketplace alone is not installation. Local marketplace and installation support varies by client/version. Follow the current OpenAI documentation for your client, then test in a new chat. Do not assume Claude's slash-command namespace applies to Codex.

### Cursor

Copy the **contents of `plugins/cursor/`**, including `.cursor-plugin/`, into a new `~/.cursor/plugins/local/vstack/` directory. Preserve any existing installation rather than overwriting it blindly. Reload Cursor and inspect the skills and rule in Customize. The Cursor marketplace manifest is for future catalog distribution, not a claim of a public listing.

### Acceptance in each host

Record the tested host/version, exact distribution commit, installation scope, observed components, and limitations. Check:

- All public skills appear once; no maintenance skills are discovered.
- Manual and contextual invocation work; installed reference links resolve without this checkout.
- `plan-work` stays read-only in a writable fixture; a bounded change workflow preserves consumer rules.
- Missing tools produce honest fallback or blocker reports.
- Cursor's rule is active in fresh sessions; context-loss behavior is observed, not assumed.
- Duplicate installations, upgrades, disabling, and removal behave predictably in new sessions.

Full domain testing of every workflow is separate from package discovery testing. No host configuration is changed by the build or checks below.

## Build and verify

Maintainers need Python 3.10+ and network access to the public pinned upstream. Git is needed only for the offline source option. No third-party Python packages are required.

```bash
python3 scripts/sync.py
python3 -m unittest discover -s tests -v
python3 scripts/sync.py --check
```

With a local upstream Git repository containing the exact pin:

```bash
python3 scripts/sync.py --source /path/to/skills
python3 scripts/sync.py --check --source /path/to/skills
```

`--source` reads committed objects at the lock's SHA, ignoring working-tree edits. `--check` rebuilds expected bytes in memory and reports missing, stale, extra, or changed generated files without writing outputs. Its default path downloads the pin; network/access failures are failures, never a successful empty result.

The generator accepts only regular archive files/directories, validates skill identities and local dependency links, and bounds archive bytes, expanded bytes, file size, member count, and total payload. It rejects symlink output paths before writing. It stages output and replaces only the three generated host directories and three catalog files, rolling back ordinary replacement errors. Run only one writer at a time in a trusted checkout: this is not a filesystem sandbox or a crash-proof transaction across all targets.

`SOURCE.json` records the upstream URL and full commit, plus SHA-256 hashes of every other file in that package (including its manifest, license, and optional rule). It excludes itself. JSON uses sorted keys, two-space indentation, UTF-8, and a final newline; no timestamps, credentials, or local paths enter output. Provenance records origin and drift; it is not a cryptographic signature or a substitute for upstream review.

## Update and release

1. Review the desired upstream commit, its public content, and license. Change `upstream.lock.json` to the full SHA; never use a branch name or moving tag.
2. Regenerate and inspect added/removed skills, adapter changes, references, and provenance. Never hand-edit generated copies.
3. Bump `VERSION` when preparing a new installable release, regenerate all host manifests, and update `CHANGELOG.md`. Claude caches versioned plugins, so changed release content needs a new version.
4. Run tests and drift checks, obtain independent review, and exercise affected host behavior. Open a PR; do not push implementation directly to `main`.
5. Merge, tagging, releases, host installation, and marketplace publication are separate authorized actions. There is no automatic publishing workflow.

For a bad local update, disable the plugin and test a known-good distribution commit before reinstalling. Never promise marketplace rollback until the selected host supports and verifies it. To add your own host-only agents or integrations later, define their source owner and tests first; don't place handwritten files inside an output directory that sync replaces.

## Automatic source updates

`.github/workflows/update-skills.yml` handles the fixed `skills-updated` repository dispatch, a daily schedule (06:17 UTC), and manual runs on `main`. It ignores dispatch payloads and independently resolves public `vllnt/skills` main. The dedicated `STACK_UPDATE_TOKEN` secret must be a selected-repository credential for **only `vllnt/stack`**, with Contents and Pull requests write access, plus **Administration read** for GitHub's [branch-protection endpoint](https://docs.github.com/en/rest/branches/branch-protection#get-branch-protection). Do not look for a Checks permission in the fine-grained personal-token UI. The workflow grants its automatically supplied, short-lived `GITHUB_TOKEN` **checks: read** and uses it only for [check-run inspection](https://docs.github.com/en/rest/checks/runs#list-check-runs-for-a-git-reference). PR creation and merging still use the dedicated token so normal PR CI is triggered. Credential authorization/setup remains with the operator. Renew the dedicated token before its chosen expiry by replacing `STACK_UPDATE_TOKEN` in both repositories. Do not substitute a personal broad token or `RELEASE_PAT`. Missing credentials fail closed. Checkout credentials are not persisted; candidate tests receive neither token. Missing built-in check credentials fail closed without falling back to the personal token.

`scripts/update_skills.py` compares complete Git objects and requires the lock to be an ancestor. Only non-executable Markdown under `workflows/` (excluding instruction files and hidden paths) and root README, changelog, and roadmap changes are ordinary. Every other path, including mandatory principles, license, code, configuration, and unknown types, stops with **MANUAL HOLD**, without publishing a candidate. A human reviews and updates sensitive changes through a separate PR.

Ordinary changes deterministically advance numeric `-dev.N` or `-canary.N`, or the patch of a stable version, regenerate all packages, and update the changelog. No pin change means no bump. The fixed `automation/update-skills` branch is published with an exact lease after isolated candidate tests. Existing candidates must exactly match reconstruction from their main-ancestor parent, pin, version, and changelog; human edits, forks, orphaned branches, draft PRs, `manual-review` labels, `MANUAL HOLD` in PR bodies, and closed unmerged automation PRs stop automation. These holds are never cleared by a newer upstream update. Closing an unmerged automation PR or deleting its branch alone intentionally keeps the stop signal.

To retire a closed, unmerged automation PR after human review:

1. Inspect its changes and resolve any desired sensitive updates through a separate human PR. Record its exact PR number and full head SHA from GitHub.
2. Preserve any needed work, then have a human delete the held `automation/update-skills` branch after confirming its current head. Automation will not delete or adopt that branch on the strength of an acknowledgement.
3. In a separately reviewed PR to `main`, append `{"pr": 123, "head": "<exact 40-character lowercase SHA>"}` to `.github/skills-update-resolutions.json` (an initially empty JSON array). Use real inspected identities, not the example. This acknowledges only that specific closed, unmerged PR; retain earlier valid entries. The updater never writes this file, and dispatch/manual inputs cannot supply a reset.
4. Merge the acknowledgement through normal review and run the updater from current `main`. Every unmerged closed automation PR needs its own exact acknowledgement. Missing/mismatched identities, another held PR, or any surviving unknown/human-edited branch still stop the run. If an acknowledged PR is later reopened or merged, remove its now-invalid entry through another reviewed main PR.

An existing ordinary open PR still requires full deterministic reconstruction before it can be updated; historical acknowledgements do not relax that proof or any live manual hold.

Before publication and merge, source and destination heads are rechecked. Merge requires the reviewed main protection contract (strict `validate` from GitHub Actions app 15368, administrators enforced, zero required approving reviews, no force pushes/deletions), observed successful checks at the exact candidate head, and a normal squash-merge API call fenced by that head. No admin bypass, direct main push, protection change, release, or marketplace publication occurs. CI and post-push PR-head propagation waiting share a bound of about five minutes. Only the exact previous generated head may be awaited while the branch ref is either that previous head or the new candidate; an unexpected head or any manual hold still stops immediately. Checks and merging require the new exact PR head. Missing, failed, skipped, or cancelled evidence leaves the PR open and fails the run. API errors and uncertain writes fail visibly rather than blindly retrying. An orphaned branch after an uncertain PR creation needs human inspection. Concurrent runs serialize without cancellation.

There is no atomic GitHub API transaction covering upstream refs, destination refs, and PR metadata. Immediate rechecks plus branch leases, merge head fences, and strict required checks narrow those races; a last-instant source update is handled on the next run. Branch protection remains the merge authority.

## Status and evidence

Automatic repository synchronization was independently verified on 2026-09-21. A fresh source push created and automatically merged a protected update PR without operator intervention. The verification candidate was source `14b8ad3dbba8ea820478d3ea2d379c2863de56d9`, merged at `3a71175c31347988861ac073417257ef1da38416`.

| Case | Hosted evidence | Observed result |
| --- | --- | --- |
| Source push | [Notifier run 35648172877](https://github.com/vllnt/skills/actions/runs/35648172877) | Delivered the fixed notification after Skills PR #14 merged. |
| Ordinary update | [Receiver run 35648191955](https://github.com/vllnt/stack/actions/runs/35648191955), [PR #7](https://github.com/vllnt/stack/pull/7), [exact-head CI](https://github.com/vllnt/stack/actions/runs/35648227825) | Created, validated, and automatically merged the regenerated update through normal branch protection. |
| Repeated run | [No-op run 35648397321](https://github.com/vllnt/stack/actions/runs/35648397321) | No pin change, version bump, PR creation, or main mutation. |
| Sensitive source change | [Hold run 35645345833](https://github.com/vllnt/stack/actions/runs/35645345833) | Expected failure before candidate creation for workflow/script changes; no automatic update PR or main mutation. |

Live testing caught a generated-help false hold and post-push PR-head propagation timing; fixes were reviewed and merged through PRs #5 and #6, with 37 regression tests passing. The fresh PR #7 case required neither manual metadata repair nor manual merge. Daily fallback is configured; its timer was not waited for. Push delivery, manual resends, automatic merging, and manual no-op execution were observed.

Claude Code 2.1.283 (2026-09-27): `claude plugin validate` passes for the catalog and plugin; a local-directory marketplace install into an isolated configuration installed `vstack@vllnt-stack` with all 22 skills, and a maintainer session with the local install listed every `vstack:*` skill. After `vllnt/stack` became public (merge `c3ad08c08fe460ed4f2e1a40630afe4001ddd23c`), an anonymous clone succeeded, and the CLI equivalents `claude plugin marketplace add vllnt/stack` plus `claude plugin install vstack@vllnt-stack` in a clean, credential-free configuration installed the plugin from the GitHub source; a headless session there listed exactly the 22 `vstack:*` skills. The same commands after merge `915a4d0d519d726f84185ec698b3ed3f4c925cb8` installed it again with its icon, updated description, and 22 skills. The in-chat `/plugin` forms were not run separately. Skill invocation behavior (including `plan-work` staying read-only), automatic skill selection, and the rest of the acceptance checklist remain unverified.

**Codex and Cursor installation, and startup/context-loss behavior in every host, remain unverified.** The repository is public and installable as a GitHub marketplace. A Claude plugin directory submission is in validation and is not listed yet. Canary builds are published as [GitHub prereleases](https://github.com/vllnt/stack/releases); releases are created manually. No automatic Claude/Codex principle loading exists.

Host format sources consulted during initialization:

- [Claude Code plugins reference](https://code.claude.com/docs/en/plugins-reference)
- [Claude Code marketplaces](https://code.claude.com/docs/en/plugin-marketplaces)
- [OpenAI plugin packaging and local marketplaces](https://developers.openai.com/plugins/build/plugins)
- [Cursor plugins reference](https://cursor.com/docs/reference/plugins)
- [Cursor local plugin testing](https://cursor.com/docs/plugins.md#test-plugins-locally)

Recheck changing host contracts before dependent updates. Source checks and simulated fixtures are not runtime acceptance.

## License

MIT. Generated skill content preserves the upstream license in each package. `SOURCE.json` identifies the exact upstream revision and packaged bytes.
