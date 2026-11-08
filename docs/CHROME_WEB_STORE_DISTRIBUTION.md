# SP145 — SmartPloy extension worldwide installation and update channel

**State: SOURCE READY, NOT PUBLISHED.** Authority: SmartPloy V4 production-first contract, FEATURE-FIRST-001, REA-FIRST-001, existing SP44 companion distribution. First-party baseline: https://github.com/galapoto/smartploy at commit 37382b54ac9257298e2d32bcd1a2733b87705f60.

## What already works, and what does not

Existing public ZIP: https://smartploy.komplyint.fi/smartploy-apply-companion.zip
Checksum: https://smartploy.komplyint.fi/smartploy-apply-companion.zip.sha256

The reviewed ZIP can be downloaded publicly from anywhere, then extracted and loaded via desktop Chrome/Chromium Developer mode → Load unpacked. Its updates require another download and manual reload. **It is NOT a Chrome Web Store install or automatically updated.**

For ordinary Chrome users on unmanaged Windows/macOS/Linux, use the official Chrome Web Store as the standard worldwide installation and browser-managed update channel. Self-hosted Chrome installation is restricted by platform/enterprise policy; a download URL alone cannot force automatic Chrome updates. Chrome checks for higher published versions and installs them when idle. Official references: https://developer.chrome.com/docs/extensions/how-to/distribute and https://developer.chrome.com/docs/extensions/develop/concepts/extensions-update-lifecycle .

## Reuse and technical changes

Original authorized donor: SmartPloy browser-companion runtime, manifest, SP44 ZIP packager, web UI, Dockerfile and CI at exact baseline above. REUSED: the unchanged original MV3 source, permissions activeTab/scripting/storage, reviewed static asset allowlist, no-remote-import policy, reproducible atomic ZIP code, public ZIP and its server release checksum gate. PORTED/ADAPTED: the same packager now emits a separate, review-only store ZIP with exactly the approved runtime files and checksum, excluding the unpacked ZIP guide and checksum text inside the extension. NEW minimal glue: CI review artifact, negative tests, verified optional store URL configuration in the existing web image and conditional Application Studio store link. Copied: none from external projects; REA_NOT_APPLICABLE to owned, fully available source. No new extension permission, host permission, runtime dependency or employer automation authorization.

## Authorized publisher release procedure

1. Get independent code/privacy/security review and green exact-commit CI. Download its GitHub Actions artifact named smartploy-chrome-web-store-[SHA] containing smartploy-apply-companion-store.zip and the matching SHA-256 sidecar. Verify with sha256sum --check inside the extracted artifact directory. CI does NOT upload or publish to any store.
2. The authorized publisher creates/uses their Chrome Web Store Developer account, enables two-step verification, accurately completes the public listing, Privacy tab, privacy policy URL, permissions explanations, support contact and actual personal-data disclosures. Never commit or share credentials or applicant data.
3. Upload the reviewed store ZIP through the Chrome Web Store Developer Dashboard and submit it for Google's review. Current MV3 manifest version is 0.5.1. Every update must increment the manifest version and be approved/published. For optional future owner-authorized API automation use the Chrome Web Store API V2 (not retired V1): https://developer.chrome.com/docs/webstore/using-api .
4. Verify the approved item is actually published under the correct extension version, permissions, owner and official URL. Obtain the 32-character public extension ID. Only THEN set protected server configuration SMARTPLOY_CHROME_WEB_STORE_ID to that exact ID and deploy the separately approved main revision using the existing SmartPloy release script. Unset/invalid ID exposes no store link; the existing ZIP remains available. Configuring an ID alone is not evidence of publication.
5. Use the real public SmartPloy UI and Chrome Web Store to install on unmanaged desktop Chrome; confirm correct permissions and safe signed-in real employer-form assistance without unintended send. Separately publish an incremented version through review and **observe a real older installed extension updating without manual unzip/reload**. Record before/after version, exact deployed SHA, negative cases and recovery. Google review/publishing and live acceptance remain operator actions; no CI run constitutes a published update.
6. Preserve the already deployed ZIP as a tested fallback. Never add remote extension JavaScript or loosen auth/consent policy to facilitate distribution. Mobile Chrome extension support is not assumed.

## Actual user acceptance — 0/3 officially verified

- [ ] EXT-01: applicant downloads ZIP from current public app, verifies exact release hash, loads and successfully uses reviewed form help on permitted employer job.
- [ ] EXT-02: owner-published official listing is live, SmartPloy app links to it, real applicants install via Chrome Web Store worldwide, and reviewed AutoApply reaches review-ready safely.
- [ ] EXT-03: real previously installed store extension is automatically upgraded by Chrome to approved higher published version; exact old/new versions and safe browser behavior are proved.

Mark SOURCE_READY, CI_QUALIFIED, APPROVED, RELEASED, USER_VERIFIED separately. Nothing here claims store publication or production installation until shown.
