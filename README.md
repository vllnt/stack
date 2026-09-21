# Vstack

One distribution repository for Vstack plugins for **Claude Code, Codex, and Cursor**.

[`vllnt/skills`](https://github.com/vllnt/skills) owns the portable workflows and principles. This repository pins an upstream commit and builds complete, committed host packages. Installed users need no Python, Git submodule, build step, or runtime source download.

## Ownership and layout

| Path | Owner / purpose |
| --- | --- |
| `upstream.lock.json` | Trusted upstream repository and immutable commit |
| `VERSION` | Shared distribution version; initially an unreleased development version |
| `scripts/sync.py` | Standard-library generator and read-only drift check |
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

## Local host testing (manual; not executed yet)

These are development instructions based on the host documentation, not claims of tested runtime compatibility. Use a synthetic project and avoid overlapping standalone skill installations. The repository is initially private; GitHub-based distribution requires access.

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

## Status and evidence

Initialization provides generated packages and structural/regression tests. **Actual Claude Code, Codex, and Cursor installation, automatic skill selection, and startup/context-loss behavior remain unverified.** No public marketplace submission, release, host installation, or automatic Claude/Codex principle loading has been performed.

Host format sources consulted during initialization:

- [Claude Code plugins reference](https://code.claude.com/docs/en/plugins-reference)
- [Claude Code marketplaces](https://code.claude.com/docs/en/plugin-marketplaces)
- [OpenAI plugin packaging and local marketplaces](https://developers.openai.com/plugins/build/plugins)
- [Cursor plugins reference](https://cursor.com/docs/reference/plugins)
- [Cursor local plugin testing](https://cursor.com/docs/plugins.md#test-plugins-locally)

Recheck changing host contracts before dependent updates. Source checks and simulated fixtures are not runtime acceptance.

## License

MIT. Generated skill content preserves the upstream license in each package. `SOURCE.json` identifies the exact upstream revision and packaged bytes.
