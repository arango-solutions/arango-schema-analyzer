# Releasing `arangodb-schema-analyzer`

This document describes how to cut a release and publish it to PyPI.

The project is set up for [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
(OIDC), so no long-lived API tokens are stored in the repo. See
`.github/workflows/publish.yml`.

> **State (2026-09-15).** Trusted publishing broke when the repository was renamed
> (`arango-schema-mapper` → `arango-schema-analyzer`): every tag-triggered run from
> 2026-07-31 to the v0.14.0 tag failed at "Publish to PyPI" with `invalid-publisher`,
> because the OIDC token's `repository` claim no longer matched PyPI's publisher entry,
> and 0.13.x/0.14.0 were uploaded with the local fallback (`scripts/publish.sh`). **The
> publisher was re-registered on 2026-09-15 and OIDC works again**: a `workflow_dispatch`
> at 15:00 UTC passed "Publish to PyPI", and a second at 20:36 UTC reached PyPI and was
> refused only with `400 File already exists` for 0.14.0 — the expected outcome for a
> version that is already published. Keep the publisher entry in step with the values in
> "One-time setup"; if a repo rename or workflow rename happens again, this is the first
> thing to check.

## One-time setup (PyPI side)

1. Sign in to <https://pypi.org> (and/or <https://test.pypi.org> for dry runs).
2. Navigate to the project, or create a **pending publisher** before the first
   upload:
   - Account → *Your projects* → *Publishing* → *Add a new pending publisher*
   - PyPI project name: `arangodb-schema-analyzer`
   - Owner: `ArthurKeen`
   - Repository name: `arango-schema-analyzer`
   - Workflow name: `publish.yml`
   - Environment name: `pypi` (use `testpypi` for TestPyPI)
3. Repeat on TestPyPI if you want dry-run uploads.

## One-time setup (GitHub side)

1. Repo → *Settings* → *Environments* → create an environment named `pypi`
   (and optionally `testpypi`). No secrets are required.
2. Recommended: add required reviewers on the `pypi` environment so every
   release requires an approval click.

## Cutting a release

1. Make sure `main` is green (CI + integration where applicable) and contains
   everything you want to ship.
2. Update the version in `pyproject.toml` (single source of truth).
3. Update `CHANGELOG.md` with a new section for the version.
4. Commit + open a PR, merge to `main`.
5. Tag the release commit on `main`:

   ```bash
   git checkout main
   git pull
   git tag -a v0.1.0 -m "Release 0.1.0"
   git push origin v0.1.0
   ```

6. The tag push triggers `.github/workflows/publish.yml`, which builds the
   sdist + wheel, runs `twine check --strict`, and uploads to PyPI via OIDC.
   Re-running the workflow for an already-published version fails with
   `400 File already exists`; that is PyPI refusing a duplicate, not a publisher problem.
7. Create a GitHub Release from the tag (optional but recommended) and paste
   the changelog section into the release notes.

## TestPyPI dry run

Before an important release, push a dry run to TestPyPI:

1. GitHub → *Actions* → *Publish to PyPI* → *Run workflow*.
2. Select branch `main`, set `target` to `testpypi`.
3. Verify the upload at <https://test.pypi.org/project/arangodb-schema-analyzer/>.
4. Install and smoke-test:

   ```bash
   python -m pip install --index-url https://test.pypi.org/simple/ \
     --extra-index-url https://pypi.org/simple/ \
     arangodb-schema-analyzer
   arangodb-schema-analyzer --help
   ```

## Building locally

```bash
python -m pip install --upgrade build twine
python -m build
python -m twine check --strict dist/*
```

This produces `dist/arangodb_schema_analyzer-<version>-py3-none-any.whl` and
`dist/arangodb_schema_analyzer-<version>.tar.gz`.

## Local publish from `.env` (fallback)

Trusted Publishing (OIDC) via the tag-triggered workflow is the recommended
path and needs no credentials (restored 2026-09-15; see the note at the top).
If you need to publish from your machine — OIDC unavailable, or the publisher
entry is mid-migration again — use the helper script, which reads a PyPI API
token from the gitignored `.env`:

```bash
# .env (never committed — see .env.example):
#   PYPI_TOKEN=pypi-...          # create at https://pypi.org/manage/account/token/
#   TESTPYPI_TOKEN=pypi-...      # optional, separate TestPyPI account, for --test

scripts/publish.sh --check   # build + `twine check --strict`, no upload
scripts/publish.sh --test    # upload to TestPyPI  (uses TESTPYPI_TOKEN)
scripts/publish.sh           # upload to PyPI      (uses PYPI_TOKEN)
```

The token is read from `.env` without sourcing the file and is passed to
`twine` only via the upload subprocess's environment (never printed, never in
`~/.pypirc`, never committed). `.env` is gitignored; keep it that way.

### Manual upload (no script)

```bash
python -m pip install --upgrade twine
python -m twine upload dist/*               # PyPI (username __token__, token as password)
python -m twine upload -r testpypi dist/*   # TestPyPI
```

Store the token in `~/.pypirc` **or** via the `TWINE_USERNAME=__token__` /
`TWINE_PASSWORD` env vars — never in the repo.

## Versioning

- Follow SemVer: `MAJOR.MINOR.PATCH`.
- Pre-`1.0.0`, bump `MINOR` for any user-visible change, `PATCH` for fixes.
- Version lives in `pyproject.toml`; update in one place only.

## Post-release checklist

- [ ] `pip install arangodb-schema-analyzer` works on a clean machine
- [ ] `arangodb-schema-analyzer --help` prints
- [ ] `python -c "import schema_analyzer; print(schema_analyzer.__all__)"` works
- [ ] GitHub Release created with notes
- [ ] `CHANGELOG.md` has an `Unreleased` section ready for the next round
- [ ] The `publish.yml` run for the tag reached "Publish to PyPI" and succeeded — if it
      failed with `invalid-publisher`, the PyPI publisher entry does not match this
      repository's owner/name/workflow/environment; fix it on PyPI before the next tag
