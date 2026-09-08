# Release netskope CLI

You are performing a full release of the netskope CLI package. This is a one-stop release workflow that pushes to GitHub (commit + tag + GitHub Release), PyPI, and updates the Homebrew tap.

## Inputs

Do not Ask the user for:
1. **Version bump type**: patch (0.2.7 → 0.2.8), minor (0.2.7 → 0.3.0), or major (0.2.7 → 1.0.0). Default: patch. If the user does not specify, assume a patch bump.
2. **Changelog entries**: the `[Unreleased]` section of CHANGELOG.md should already hold them, since every PR adds its own. Check `git log v<last>..HEAD` for anything missing and add it before releasing.

## Steps

### 1. Determine the new version
- Read the current version from `pyproject.toml` (field `version`)
- Compute the new version based on the bump type
- Find the previous release tag (`git tag --list | sort -V | tail`) and review `git log <last-tag>..HEAD` to build the changelog bullets

### 2. Update version in ALL FOUR places, then refresh the lockfile
- `pyproject.toml` → `version = "X.Y.Z"`, then run `uv lock`: `uv.lock` records the project's own version, and `uv lock --check` / `uv sync --locked` fail until it is refreshed
- `src/netskope_cli/main.py` → `__version__ = "X.Y.Z"`
- `docs/index.html` → TWO spots: the header badge (`<span class="badge badge-blue ml-1">vX.Y.Z</span>`) and the "Verify installation" example output (`netskope-cli X.Y.Z`). After editing, `grep -n "<old-version>" docs/index.html` to confirm nothing was missed.
- Also validate that the rest of docs/index.html and the README don't need updates for this release's changes (new commands, changed flags, etc.). If they do, update them.

### 3. Update CHANGELOG.md
The file follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/) throughout.
- Rename `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD` and insert a fresh, empty `## [Unreleased]` above it.
- Entries sit under `### Added`, `### Changed`, `### Deprecated`, `### Removed`, `### Fixed` and `### Security`, in that order, one or two sentences each; drop empty subsections.
- Update the reference links at the bottom of the file: point `[Unreleased]` at `compare/vX.Y.Z...HEAD` and add `[X.Y.Z]: https://github.com/netskopeoss/netskope-cli/compare/v<previous>...vX.Y.Z`.

### 4. Lint, format, type-check, test
```bash
uv run ruff check . --fix
uv run ruff format .
uv run ty check
uv run pytest
```
- If there are lint errors that can't be auto-fixed, stop and report them.
- ty must report 0 diagnostics and ALL tests must pass before continuing. If not, stop and report the issue — fix before continuing.

### 5. Commit, push, tag, and create the GitHub Release
```bash
git add pyproject.toml uv.lock src/netskope_cli/main.py CHANGELOG.md docs/index.html
# Also add any other files modified in this session
git commit -m "Release vX.Y.Z - <short summary>"
git push origin master

# Annotated tag, pushed to GitHub
git tag -a vX.Y.Z -m "vX.Y.Z - <short summary>"
git push origin vX.Y.Z

# GitHub Release notes are the version's CHANGELOG section, verbatim
awk '/^## \[X.Y.Z\]/{f=1; next} /^## \[/{f=0} f' CHANGELOG.md > /tmp/release-notes.md
gh release create vX.Y.Z --repo netskopeoss/netskope-cli --title "vX.Y.Z" --notes-file /tmp/release-notes.md
```

### 6. Publish to PyPI (CI, triggered by the tag)
Pushing the `vX.Y.Z` tag in step 5 starts `.github/workflows/release.yml`: it checks that the tag matches the project version, runs the same checks as CI, builds, and publishes with `uv publish --trusted-publishing always`. Authentication is PyPI's Trusted Publisher for this repository (workflow `release.yml`, environment `pypi`), so no token is involved.
```bash
gh run watch --repo netskopeoss/netskope-cli --exit-status \
  "$(gh run list --repo netskopeoss/netskope-cli --workflow release.yml --limit 1 --json databaseId -q '.[0].databaseId')"
```
- Wait for the run to succeed before continuing. If the publish step fails, fix the cause and `gh run rerun` it; PyPI rejects duplicate files rather than corrupting anything.
- Fallback only, when Actions cannot run (outage, publisher not registered yet): publish locally with the keychain token.
```bash
rm -rf dist   # uv publish uploads everything in dist/, so the previous release's files must go first
uv build
token="$(security find-generic-password -s pypi-netskope -w)" || { echo "keychain item pypi-netskope not found" >&2; exit 1; }
[ -n "$token" ] || { echo "empty PyPI token" >&2; exit 1; }
UV_PUBLISH_TOKEN="$token" uv publish --check-url https://pypi.org/simple/
```
- The token comes from the macOS keychain entry set up once per CLAUDE.md; never echo it. A missing or empty token must stop here: uv would otherwise upload with blank credentials and PyPI's 403 would arrive after the tag and GitHub Release are already public.
- `--check-url` lets a retry skip files PyPI already has instead of failing on the first duplicate.

### 7. Update the Homebrew tap
- Sync the local tap first: `cd ../homebrew-tap && git pull --ff-only origin main`
- Fetch the new sdist URL and SHA256 from `https://pypi.org/pypi/netskope/X.Y.Z/json` (the `urls` entry with `packagetype == "sdist"`)
- Edit `Formula/netskope.rb` in the local tap repo at `../homebrew-tap/` (relative to the CLI repo)
  - Update the top-level `url` line with the new sdist URL
  - Update the top-level `sha256` line with the new hash
- **Check every resource block, not just the top-level url**: from the CLI repo, run `uv export --no-dev --no-hashes --no-emit-project --format requirements-txt` for the runtime dependency set (outside the repo `uv pip list` silently describes some other interpreter, and the dev venv holds packages such as `click`, pulled in by black, that are not runtime resources). Compare it with the formula's `resource` blocks in both directions: add a block for every new package, delete the block for every package that is gone, and refresh URL + SHA256 from `https://pypi.org/pypi/<name>/<version>/json` for every version change.
- Homebrew installs the sdist with pip's `--no-binary=:all:`, which also builds the build backend from source. hatchling is pure Python so that is quick; do not move to a compiled backend (uv_build, maturin) without re-testing the formula. After the sdist is on PyPI and the formula is pushed, run `brew install --build-from-source netskopeoss/tap/netskope` before announcing. Homebrew passes `--uploaded-prior-to=P1D` to pip and refuses PyPI files younger than 24 hours, so this check, and any user's `brew install` of the new version, only works the day after `uv publish`; time the announcement accordingly.
  - Note: pip freeze shows jaraco packages with dots (`jaraco.context`) while the formula uses dashes (`jaraco-context`) — normalize names before comparing or you'll get false mismatches.
  - Note: Linux-only deps (e.g. `cryptography` via secretstorage) won't appear in a local macOS pip freeze and are not formula resources — skip them.
- Commit and push the tap:
```bash
cd ../homebrew-tap
git add Formula/netskope.rb
git commit -m "Update netskope to X.Y.Z"
git push origin main
```

### 8. Verify
- Confirm the new version is live on PyPI. Note: `https://pypi.org/pypi/netskope/json` (unversioned) is CDN-cached and may show the old version for a few minutes — use the versioned endpoint `https://pypi.org/pypi/netskope/X.Y.Z/json` (should list 2 files) or `https://pypi.org/simple/netskope/` instead.
- Confirm the tag and GitHub Release exist: `gh release view vX.Y.Z --repo netskopeoss/netskope-cli`
- Confirm the tap repo on GitHub has the updated formula (e.g. `gh api repos/netskopeoss/homebrew-tap/contents/Formula/netskope.rb`)
- Print a summary of what was done

## Important
- Never hardcode or echo API tokens, PyPI tokens, or secrets
- If any step fails, stop and report the error — do not continue blindly
- Always run ruff check, ruff format, ty, and the test suite before committing
- `uv.lock` is committed. A dependency bump edits the pin in `pyproject.toml` and then runs `uv lock`; commit both files together
