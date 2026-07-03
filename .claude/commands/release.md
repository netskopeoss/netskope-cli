# Release netskope CLI

You are performing a full release of the netskope CLI package. This is a one-stop release workflow that pushes to GitHub (commit + tag + GitHub Release), PyPI, and updates the Homebrew tap.

## Inputs

Do not Ask the user for:
1. **Version bump type**: patch (0.2.7 → 0.2.8), minor (0.2.7 → 0.3.0), or major (0.2.7 → 1.0.0). Default: patch. If the user does not specify, assume a patch bump.
2. **Changelog entry**: A short summary of what changed in this release. Derive bullet points from the commits and diff since the last release tag (`git log v<last>..HEAD`), not just the working tree.

## Steps

### 1. Determine the new version
- Read the current version from `pyproject.toml` (field `version`)
- Compute the new version based on the bump type
- Find the previous release tag (`git tag --list | sort -V | tail`) and review `git log <last-tag>..HEAD` to build the changelog bullets

### 2. Update version in ALL FOUR places
- `pyproject.toml` → `version = "X.Y.Z"`
- `src/netskope_cli/main.py` → `__version__ = "X.Y.Z"`
- `docs/index.html` → TWO spots: the header badge (`<span class="badge badge-blue ml-1">vX.Y.Z</span>`) and the "Verify installation" example output (`netskope-cli X.Y.Z`). After editing, `grep -n "<old-version>" docs/index.html` to confirm nothing was missed.
- Also validate that the rest of docs/index.html and the README don't need updates for this release's changes (new commands, changed flags, etc.). If they do, update them.

### 3. Update CHANGELOG.md
- Prepend a new entry at the top (below the header) with format:
```
## [X.Y.Z] - YYYY-MM-DD

- bullet points describing the release
```
- If CHANGELOG.md does not exist, create it with a `# Changelog` header first.

### 4. Lint, format, type-check, test
```bash
poetry run ruff check . --fix
poetry run black .
poetry run mypy src/
poetry run pytest
```
- If there are lint errors that can't be auto-fixed, stop and report them.
- mypy must report 0 errors and ALL tests must pass before continuing. If not, stop and report the issue — fix before continuing.

### 5. Commit, push, tag, and create the GitHub Release
```bash
git add pyproject.toml src/netskope_cli/main.py CHANGELOG.md docs/index.html
# Also add any other files modified in this session
git commit -m "Release vX.Y.Z - <short summary>"
git push origin master

# Annotated tag, pushed to GitHub
git tag -a vX.Y.Z -m "vX.Y.Z - <short summary>"
git push origin vX.Y.Z

# GitHub Release with the changelog bullets as notes
gh release create vX.Y.Z --repo netskopeoss/netskope-cli --title "vX.Y.Z" --notes "<changelog bullets>"
```

### 6. Build and publish to PyPI
```bash
poetry build
poetry publish
```
- Wait for publish to succeed before continuing.

### 7. Update the Homebrew tap
- Sync the local tap first: `cd ../homebrew-tap && git pull --ff-only origin main`
- Fetch the new sdist URL and SHA256 from `https://pypi.org/pypi/netskope/X.Y.Z/json` (the `urls` entry with `packagetype == "sdist"`)
- Edit `Formula/netskope.rb` in the local tap repo at `../homebrew-tap/` (relative to the CLI repo)
  - Update the top-level `url` line with the new sdist URL
  - Update the top-level `sha256` line with the new hash
- **Check every resource block, not just the top-level url**: compare each `resource "<name>"` version in the formula against `poetry run pip list --format=freeze`. For any runtime dependency whose version changed, fetch its new sdist URL + SHA256 from `https://pypi.org/pypi/<name>/<version>/json` and update that resource block.
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
- Always run linting, formatting, mypy, and the test suite before committing
- Remember `poetry.lock` is gitignored in this repo — Dependabot scans `pyproject.toml` constraints, and lockfile changes never appear in commits
