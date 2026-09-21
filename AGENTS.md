# Vstack distribution

This repository packages Vstack for Claude Code, Codex, and Cursor. `vllnt/skills` owns portable skill content; `upstream.lock.json` selects its immutable commit. Do not edit upstream or generated skill copies here.

- `scripts/sync.py` owns host manifests, marketplace catalogs, generated packages, and the Cursor principles adapter. `VERSION` owns the shared package version.
- `plugins/{claude,codex,cursor}/` and the three host marketplace JSON files are generated and committed. Change the pin or generator, then regenerate; do not hand-edit output. Preserve unrelated plugin directories.
- Keep host integration separate from consumer permissions and architecture. Do not add hooks, services, or automatic principle activation for another host without evidence and an explicit request.
- Verify with `python3 -m unittest discover -s tests -v` and `python3 scripts/sync.py --check`, then `git diff --check`. `--source /path/to/skills` checks the pinned local Git objects offline, not working-tree edits.
- Review generated public content, source attribution, and relevant success/failure behavior before upload. Use independent review for substantive changes and rerun affected checks after repairs.
- Work through branches and PRs; no direct implementation pushes to `main`. Merge, release, marketplace publication, and host installation need their own authority.
- Keep `CHANGELOG.md` current. Record runtime evidence and gaps in `README.md`; structural validation never proves host loading.
