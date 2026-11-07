# SmartPloy Chrome Apply Companion — installation, updates and release channels

**Status:** source v0.7.0, reviewed CI candidate; production availability must be
verified by the exact deployed version. The browser extension is a client
installed in the user's browser. Deploying SmartPloy server-side cannot
silently install or update users' copies.

## Desktop Chrome/Chromium — install now from reviewed release ZIP

1. Open the exact-head GitHub Actions run of the SmartPloy candidate; download
   the artifact named `smartploy-apply-companion-<commit SHA>`.
   The artifact contains `smartploy-apply-companion.zip` and its
   `.sha256` digest. Extract that **inner** ZIP into a permanent folder,
   e.g. `~/Applications/SmartPloy-Companion/`. Do not delete this folder.
2. Visit `chrome://extensions`, turn on Developer mode and select
   **Load unpacked**. Select the folder containing `manifest.json`.
   Confirm the displayed version and pin the toolbar icon.
3. Sign into the current SmartPloy website in that same browser, review your
   job-specific CV, full application and applicant profile, create a short-lived
   reviewed packet, and run the extension **Verify review** action in the
   SmartPloy tab. Open the matching employer form in a new tab, choose
   **Inspect**, confirm reviewed ordinary fields, then **Fill**. For PDFs
   separately choose the exact job-approved CV PDF and explicitly approve
   attachment. Other questions, consent, auth/MFA/CAPTCHA, employer terms and
   the final submit remain applicant actions, except separately commissioned
   exact Lever final-action rights.

**Persistence:** Load unpacked remains installed across Chrome restarts while
the extracted folder exists and the extension is enabled. It is not
Chrome-Web-Store signed and does **not** automatically update. To modify code,
edit a reviewed local copy, then click **Reload** on `chrome://extensions`
(or replace folder contents from the new verified ZIP and click Reload).
Manual modifications are local, not verified publisher releases and may break
the review/security contract; prefer upstream changes, tests and a version bump.

## First-party deployment channel — release per feature

When the correct SmartPloy SHA is independently approved and deployed,
`https://smartploy.komplyint.fi/smartploy-apply-companion.zip`
and `.zip.sha256` must be served by the production web image. Verify the
public SHA, the archive's Manifest V3 version, active-tab-only permissions and
the authenticated sign-in/review/attach flow against the exact deployed SHA.
Do not treat a green isolated Compose or PR artifact as a live release.

The CI downloadable ZIP is a testable **release candidate** and expires after
30 days. A permanent update distribution cannot rely on GitHub Actions
artifacts.

## Managed automatic updates

**Preferred for general users:** Publish through a publisher-owned Chrome Web
Store developer account (possibly Unlisted initially). Supply screenshots,
support/privacy policy and genuine functionality/permission disclosure.
Version each change (`0.7.1`, `0.8.0`, etc.) while keeping the extension ID,
publisher identity and normal signed update channel. Review/publication delays
and installed-browser update propagation are external and cannot be promised
instantaneously. This route needs the developer's publisher credentials,
store-review approval and actual acceptance before being called delivered.

**Enterprise-managed alternative:** for managed Linux/ChromeOS/enterprise
environments, use a policy-approved signed CRX with stable signing key and
HTTPS update manifest/ExtensionInstallForcelist where supported. Distribution
policies vary by OS and organization; test policy/identity/channel thoroughly.
Do not embed signing keys in GitHub or product images or ask users to disable
Chrome extension security controls.

**For fast internal QA:** keep the unpacked folder and reload after replacing
from a newly reviewed ZIP. This is durable on the local machine but requires
manual updates.

## Future feature-first contract

For each extension feature: pin source/revision, test Chrome original popup +
injected callbacks + PDF digest, maintain version/host/permission review and
backwards-compatible server handoff, publish a *new extension artifact* and the
server release independently, update the intended delivery channel, and
verify a real browser install/update and one user action. A feature becomes
`USER_VERIFIED` only after its intended users can actually use it.
