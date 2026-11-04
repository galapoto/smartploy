# SP130 — SmartPloy FEATURE-FIRST-001 continuous production promotion

**Status: source candidate, not commissioned or live.** This PR does not grant
production credentials or silently merge other PRs. It implements a
least-privilege, **feature-by-feature** CI → production route *after* the
required trust gates. The current live running SHA is unknown in this session.

## Trigger and product outcome

Every independently reviewed feature merged to protected `main` triggers
`Smartploy CI`. As soon as its **exact push-to-main** run passes all five
jobs (Python/PostgreSQL, web, Chromium, isolated deploy-stack and exact-source
receipt), `.github/workflows/feature-first-production.yml` qualifies its
40-hex SHA and invokes the trusted production relay **for that SHA only**.

The relay waits a bounded interval for native Woodpecker's exact-SHA PASS;
a separate trusted release-classification authority must declare the same SHA
either `feature-first-auto-eligible-sha` (reviewed low-risk feature) or
`feature-first-approved-sha` (explicit high-risk feature). The operator may
choose stricter GitHub environment protection. No worker/pr build can write
these receipts or run production code.

After qualification, reuse the host's original
`deploy/personal/scripts/deploy.sh` for preflight, clean immutable main
checkout, database backup, migrations, Docker image rebuild, worker health,
OIDC/public exact web parity, extension ZIP, and release-evidence checks.

Successful GitHub production job + host evidence = **RELEASED pending
user-role browser acceptance**, never automatically `USER_VERIFIED`/`SHIPPED`.
Actual UI must be tested under the intended signed-in roles (desktop/mobile,
light/dark, profile isolation, CV → Manual/Assisted/Automatic, etc.).

## Initial one-time commissioning (authorized host operator only)

The GitHub connector in this session can write code and test it but **cannot
install a production SSH identity, alter protected environments or connect to
the `obum-core-01` sudo/Docker host**. One authorized operator must
commission the transport. Do not paste any key, JWT, CV or database value into
GitHub/ChatGPT.

1. Independently review and merge this narrow delivery-adapter PR.
   Configure `main` branch protection and require the existing five CI checks
   and independent code review before merge. Qualify exact resulting main SHA
   in the native Woodpecker `obum-delivery` system before release.
2. On the trusted OVH host, install the reviewed versions of
   `feature-first-remote-promotion.sh` at root-owned
   `/usr/local/sbin/smartploy-feature-first-dispatch`, and
   `feature-first-ssh-gate.sh` at root-owned
   `/usr/local/libexec/smartploy-feature-first-ssh-gate`,
   both non-writable by other users. This initial installation is not a
   feature deployment.
3. Provision a dedicated locked-password `smartploy-cd` SSH account with a
   separate ED25519 deploy key. Its `authorized_keys` entry must use
   `restrict,command="/usr/local/libexec/smartploy-feature-first-ssh-gate"`.
   The forced command accepts only `feature-first-deploy <40 hex SHA>`.
   Only the exact installed root dispatcher is permitted via sudo, using
   a narrowly reviewed `/etc/sudoers.d/smartploy-feature-first` entry,
   not `sudo bash`, `sudo -i`, arbitrary Git, arbitrary Docker, or wildcard
   shell commands. Verify with `visudo -c` and a deliberate invalid SSH
   command (expected RED).
4. GitHub Settings → Environments → `smartploy-production`: restrict to
   protected `main`, add any required independent approvers supported by
   the repository's GitHub plan, and store the **environment-specific** secrets
   `SMARTPLOY_PRODUCTION_SSH_PRIVATE_KEY` and
   `SMARTPLOY_PRODUCTION_KNOWN_HOSTS` (the latter manually fingerprint-
   verified against the trusted host). Configure environment variables
   `SMARTPLOY_PRODUCTION_HOST`, `SMARTPLOY_PRODUCTION_SSH_USER` and
   `SMARTPLOY_PRODUCTION_SSH_PORT`. Never use unverified `ssh-keyscan`.
   The release workflow uses no SSH key for PRs or the qualify job.
5. Commission native Woodpecker → trusted host proof:
   `native-ci-qualified-sha` must be written **only** on positive and
   expected-RED-confirmed native CI for the exact protected main SHA.
   Independently classify low-risk reviewed features with
   `feature-first-auto-eligible-sha`; sensitive releases (identity,
   permissions, automated employer actions, message/PII schema changes)
   require explicit `feature-first-approved-sha`.
   These are root-owned, non-symlinked, non-group-writable files in the
   configured private deploy-state directory, containing only one exact SHA.
   This repo intentionally contains **no implementation that self-writes these
   approvals**. Configure the trusted ObumDelivery adapter or designated
   operator first. A green GitHub Actions run cannot satisfy native proof.
6. After a synthetic good-SHA success and bad-SHA / PR-SHA / wrong-host /
   unapproved-SHA negative-control drill, set repository **variable**
   `SMARTPLOY_FEATURE_FIRST_AUTO_DEPLOY=true`. It is OFF by default.
   Protected `main` merges now attempt immediate, one-feature-at-a-time
   release automatically. Root host retains its existing production
   `production-operation.lock` and release-state provenance.

## Trust, failure, and rollback

- `workflow_run` is triggered from CI *completion*. Admission rejects PR,
  fork, manual dispatch, skipped/failing jobs and wrong SHA. Do not count
  PR-head CI as post-merge CI.
- The secret-bearing job does **not** check out or execute repo scripts. It
  connects to the forced-command SSH identity, which has no arbitrary root
  shell, SSH forwarding, pty or agent-forwarding privileges.
- Root dispatcher is installed from a separately reviewed source and
  root-owned outside the mutable working tree. It checks the native CI proof,
  risk approval and forward-only ancestry of the recorded previous release.
  It cannot authorize itself.
- No automatic re-deploy of an older/rolled-back commit. Failed receipts,
  dirty source, missing credentials, SSH host-key change, native CI failure,
  competing production lock, missing verified provider identity or schema
  issues are **HOLD**. Never silently turn a red result green or use
  `continue-on-error` to mask a deployment failure.
- The host uses its existing backup/restore and immutable SHA rollback
  scripts. Auto-rollback of schema/PII is not enabled; authorized operator
  chooses and verifies recovery from known-good image/backup.
- Authenticated cross-account and UI acceptance may still require a human.
  Record `SOURCE_READY → CI_QUALIFIED → RELEASED → USER_VERIFIED` with
  deployed-sha, image IDs, backup and public parity. Never label deployed-dark,
  fixture-only or pending approval as shipped.

## Present application

The premium UI #294 is the **first recommended low-risk production target**.
Independent review and protected merge must finish, then the native bridge and
host must be commissioned. Social messaging #295, moderation #296 and any
automatic employer interaction need their own privacy/abuse reviews and
higher-risk approvals. This adapter never performs employer submissions.

## REA-first source decision

Reused SmartPloy's original `deploy.sh`, online release-evidence/health
checks, stable per-SHA manifest, Woodpecker and GitHub Actions. Original
GitHub event validator and forced-command wrapper are the only new pieces.
Official upstream GitHub Actions environments/workflow_run guidance consulted;
no copied award-site code, unlicensed binaries or cross-repo credentials.

REA executable runtime: **REA_BLOCKED** in the current connector session.
Measured time saving: **unknown**. No production SSH/CI credential obtained
or live deployment claimed.
