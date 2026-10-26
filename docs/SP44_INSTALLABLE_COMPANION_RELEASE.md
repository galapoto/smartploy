# SP44 — First-party installable Chrome companion, bundled into verified web release

**Date:** 26 October 2026 (Finland)
**Baseline:** SP43 main `c10ab5dec259ef2699ce6357e50093ed887633e3`.
**Part:** SP21 P0-C installable browser handoff / end-user activation; ObumDelivery artifact provenance.
**Status:** reviewed source and release tests. Running OVH release requires separate native Woodpecker/OIDC acceptance.

## The actual blocker

SP41–SP43 implement reviewed browser form assistance for Lever, Ashby and
selected Greenhouse hosted jobs. The application editor linked only to GitHub
source instructions, forcing every applicant to clone the whole development
repository or fetch its contents. This prevented an ordinary applicant from
activating the assisted browser workflow even when a production backend and
source-current CV-first drafts were available.

SP44 delivers a direct **Download Chrome companion ZIP** on the first-party
*My applications → Fill the employer's form* screen. The exact same
reviewed extension modules are deterministically packaged in the
production web Docker build. The package and its independent SHA-256 sidecar
are served as static assets from the SmartPloy domain without private APIs,
CV data, user token, or background access. No third-party extension store or
external hosted runtime is needed.

## Source reuse vs original code

**Reused unchanged:** existing `browser-companion/*.mjs` original MV3 popup
and icon, all SP41–SP43 field/question/PDF review gates, existing
`ApplicationStudio` signed-in user workflow and existing immutable Caddy
web image, Docker Compose release tests, Node/Chromium regression suite.

**New original code:** stdlib-only `web/scripts/package_companion.py`, two
automatic `npm` lifecycle packaging hooks, one review-bounded Docker
source-copy, Caddy ZIP route, SmartPloy UI link/instructions, Python negative
security tests, synthetic Chromium downloadable ZIP/hash checks and Docker
image-served SHA256 verification. No new npm/Python application dependencies,
worker engine, database migration, Chrome host permissions, employer login,
model invocation, or automatic job submission rights.

## Artifact and permission requirements

- Fixed explicitly reviewed archive members: 15 existing MV3 source files,
  `INSTALL.txt` and `SHA256SUMS.txt`. No `tests/`, repository data,
  `.env`, private documents, Git metadata, node_modules or build leftovers.
- Deterministic `ZIP_STORED` contents, fixed timestamps/file modes and
  lexically sorted entries; independently downloadable
  `smartploy-apply-companion.zip.sha256` for binary integrity.
- Build fails closed if any reviewed source is missing, symlinked, oversized,
  has an unapproved static import/HTML asset or requests broader MV3
  privileges. Required permissions **exactly**
  `activeTab`, `scripting`, `storage`; no `host_permissions`,
  `background`, `content_scripts`, `update_url` or extra install scope.
- Web Docker build stage installs Python solely to run the stdlib packager,
  then copies **only `dist/`** into the final Caddy image. The final
  static ZIP does not contain build-stage Python or source tests.
- Caddy handles exact `.zip`/`.sha256` paths before generic SPA
  `try_files`, with `Cache-Control: no-store`. Missing ZIP returns HTTP
  404 rather than misleading HTML even when SPA routes normally fall back.
- Chrome installation: **desktop** Chrome/Chromium, save ZIP, extract,
  `chrome://extensions` → Developer mode → Load unpacked → folder containing
  `manifest.json`. Not a Chrome Web Store install, signing or auto-update.
  A released update requires the applicant to download/reload it. No claim
  of real device installation until signed-in Chrome acceptance.

## End-to-end safety and tests

1. Python deterministic same-source packaging twice, exact SHA256 checksum,
   no forbidden archive members, cross-checked file bytes, real MV3 manifest,
   install text and checksums.
2. Negative controls mutate a *temporary copied source* to introduce
   broad host permission, background service worker, remote JS import,
   unknown local JS dependency, symlink or remote HTML asset. Every case
   must fail before public artifact creation.
3. React Studio test confirms first-party ZIP link, correct download file,
   desktop Load unpacked guidance and **zero employer/packet API actions**
   from rendering or downloading.
4. Real production Vite/Chromium synthetic tests request `/smartploy-apply-companion.zip`
   and checksum from the built preview. Assert ZIP signature, non-HTML type,
   SHA256 match and no required auth or external source.
5. Synthetic Compose production web image serves the real ZIP via Caddy;
   independently verifies SHA256, archive and manifest permissions.
6. Full exact PR-head CI, expected-head merge and independent main CI.
   Native ObumDelivery release, guarded OVH deploy and physical Chrome
   acceptance remain independent.

## Explicit limitations / next critical gates

- This milestone **delivers a path to install** the reviewed companion;
  it does not itself send applications, enable provider rights, activate
  production, bypass employer consent, or make the extension auto-update.
- `/healthz` public site was last observed with ready Postgres/workers but
  missing source `release_revision`; this is not evidence that SP44
  has reached OVH. Release operator must pin exact tested main SHA, run
  native Woodpecker approval, backup/migrate/recreate/verify/rollback and
  assert the exact public health revision plus ZIP checksum/Chrome QA.
- Browser extension Chrome Web Store signing/public distribution and
  independently employer-authorized submit rights remain separately gated.
  Users can still manually submit and self-report.
