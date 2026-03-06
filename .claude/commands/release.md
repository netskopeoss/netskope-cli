# Release netskope CLI

You are performing a full release of the netskope CLI package. This is a one-stop release workflow that pushes to GitHub, PyPI, and updates the Homebrew tap.

## Inputs

Do not Ask the user for:
1. **Version bump type**: patch (0.2.7 → 0.2.8), minor (0.2.7 → 0.3.0), or major (0.2.7 → 1.0.0). Default: patch. If the user does not specify, assume a patch bump.
2. **Changelog entry**: A short summary of what changed in this release. You should figure bullet points or a sentence based on the git diff for this release.

## Steps

### 1. Determine the new version
- Read the current version from `pyproject.toml` (field `version`)
- Compute the new version based on the bump type

### 2. Update version in both places
- `pyproject.toml` → `version = "X.Y.Z"`
- `src/netskope_cli/main.py` → `__version__ = "X.Y.Z"`
- update the version in the netskope-cli/docs/index.html. Validate that nothing needs to change in this file. If the guide needs to be tweak, please do so.
- Also validate that the readme doesn't need to be updated. If it does, update it.

### 3. Update CHANGELOG.md
- Prepend a new entry at the top (below the header) with format:
```
## [X.Y.Z] - YYYY-MM-DD

- bullet points from user input
```
- If CHANGELOG.md does not exist, create it with a `# Changelog` header first.

### 4. Lint and format
```bash
poetry run ruff check . --fix
poetry run black .
```
- If there are lint errors that can't be auto-fixed, stop and report them.
- Verify ALL tests pass before continuing, if not stop and report the issue. You will have to fix before continuing. 

### 5. Commit and push to GitHub
```bash
git add pyproject.toml src/netskope_cli/main.py CHANGELOG.md
# Also add any other files the user modified in this session
git commit -m "Release vX.Y.Z - <short summary>"
git push origin master
```
Tag this build in github with the release tag.

### 6. Build and publish to PyPI
```bash
poetry build
poetry publish
```
- Wait for publish to succeed before continuing.

### 7. Update the Homebrew tap
- Fetch the new sdist URL and SHA256 from `https://pypi.org/pypi/netskope/X.Y.Z/json`
- Edit `Formula/netskope.rb` in the local tap repo at `../homebrew-tap/` (relative to the CLI repo)
  - Update the `url` line with the new sdist URL
  - Update the `sha256` line with the new hash
- Check if any Python dependency versions changed by comparing installed versions. If dependencies changed, regenerate the resource blocks.
- Commit and push the tap:
```bash
cd ../homebrew-tap
git add Formula/netskope.rb
git commit -m "Update netskope to X.Y.Z"
git push origin main
```

### 8. Verify
- Confirm the PyPI page shows the new version
- Confirm the tap repo has the updated formula
- Print a summary of what was done

## Important
- Never hardcode or echo API tokens, PyPI tokens, or secrets
- If any step fails, stop and report the error — do not continue blindly
- Always run linting and formatting before committing
