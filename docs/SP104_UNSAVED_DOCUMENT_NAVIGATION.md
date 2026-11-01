# SP104 — No silent loss of CV and cover-letter edits

**Date:** 2026-11-01 (Finland)  
**Plan/baseline:** source `f7a3f4098c40593d405681f71134dafdc683b303`, stacked after reviewed-but-not-merged SP101–SP103 PR #270. No change to employer submission authorization. This branch targets the parent feature branch so PR #270's green review head remains unchanged.

## User goal and behavior

Users can write a complete CV and full application cover letter in two owner-private first-party editors. Previously, their own Reload/current-draft switching warned about unsaved text, but sidebar navigation, header search, global refresh, CV replacement or browser refresh could silently discard edits.

SP104 extends only the existing **dirty-state** signals and `window.confirm` design:
- Master CV editor reports unsaved text vs the last verified saved text.
- Application Studio reports unsaved job-specific CV or cover-letter text vs the selected saved workspace revision.
- Parent App checks only **ephemeral booleans** before in-app page navigation, header job search, global refresh and uploading a replacement CV. Declining a navigation preserves the exact private editable text in the mounted component.
- Native `beforeunload` warns for browser refresh, tab close or same-tab external navigation. The browser, not SmartPloy, owns that prompt.
- The Application Studio refresh button also confirms before reloading a dirty workspace.
- A verified master-CV save clears the parent dirty flag before the CV-first post-save handoff. Account switches clear both flags immediately.
- The guard does **not** intercept off-page work in a new tab, affect server-side saved documents, create automatic drafts, approve profile facts or authorize employer submission.

## REA/reuse decision

`REA_NOT_APPLICABLE` — directly reusable, readable first-party source already exists in `web/src/ApplicationStudio.tsx` (`pick`/inbox draft confirmations and `dirty`) and `web/src/MasterCVEditor.tsx` (reload and save confirmation). No external executable/binary, third-party UI code, or API recording is needed; no protected code or assets copied. Design copies only owned, established confirmation patterns. No new dependency. Tool version/reverse-engineering evidence: not applicable. Engineering savings `unknown` (no comparable measured baseline).

## Acceptance and limitations

Run `web` Vitest and browser acceptance plus full repository CI. New tests check denied and accepted sidebar exit, header-search exit, browser unload only while dirty, CV upload gate, master-CV cleanup after save and job-specific refresh prompt. Existing identity isolation and exact-hash CV write safety remain in place.

**Source-only until proven otherwise:** require exact-SHA GitHub checks, separate reviewer and owner approval, native ObumDelivery checks where mandated, post-merge main CI and a guarded, backed-up OVH deploy with real signed-in two-owner acceptance. No production access, live employer calls, external submission, cross-account clipboard or unsaved personal-document storage is added. Browser beforeunload dialogs are browser-dependent and may not appear in every mobile client; existing in-app confirmation remains the deterministic gate.

## Account-switch preflight (security-critical)

The global Refresh button checks server-issued identity **before** showing an unsaved-edit discard prompt. If the owner subject changed, is missing or cannot be verified, it clears the previous private editor immediately and re-loads as the new identity (or fails closed). This reuses the original `sessionIdentity`, `getSession`, `clearPrivateWorkspace` and `load` controls, rather than allowing an old user's unsaved document to block identity reconciliation. A synthetic same-email/different-user regression proves an account change always wins over the discard dialog. Normal same-owner refreshes still ask before discarding unsaved document text.
