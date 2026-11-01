# SP100 — Prismatic Northstar first visual slice (review only)

**Baseline:** `804747bd9f01f999f9e806dcf96459bb215bb8f1` (main, 1 Nov 2026).  
**Branch:** `design/northstar-prismatic-first-slice-20261101`.  
**Scope:** a new CSS layer imported last from `web/src/main.tsx`; no React, backend, document, identity, worker, employer-provider or database changes.

## Decision

Blend the user-provided Prismatic UI foundations with established SmartPloy (SP99): dark/light support, original complete SmartPloy logo and panorama, CV-first navigation, Manual / Assisted / Automatic, complete document editing and independent authorized review before any employer send. Northstar uses a glacial-teal/navy paper metaphor, purposeful card depth, a four-stage journey and typographic hierarchy. Bricolage Grotesque is a **display-only optional family**, falling back to existing DM Sans until licensing/privacy-reviewed self-hosting. There is no third-party font request or added runtime dependency in the patch.

## Why a CSS-only first slice

- Avoid rewriting working components and risking a regression in CV upload, OIDC tenant/revision isolation, ATS matching, applicant review or employer authorization.
- Existing SP99 theme state and CSS continue to handle dark mode; this layer supplies token and component-specific overrides after the existing cascade.
- Reversible one-import change. Disabled mode cards have no hover elevation; review and submit rights are unchanged.
- Shadows, 18px card corners, 44px action controls, visible focus and reduced-motion guard add distinctive but comprehensible structure.
- The original Finnish panorama is *not* replaced or covered with headline text.

## REA-FIRST-001

**Status: REA_NOT_APPLICABLE.** Reviewed authorized first-party UI and task/source rules plus the user-supplied Prismatic architecture/recipes. No opaque binary, third-party executable, protected website or API recording needed reverse analysis; no REA tool was used. **Reuse:** all existing application logic, CV/editors, theme toggler, sidebar, portrait/banner, employer guards; Prismatic semantic tokens/profile combination. **New:** standalone CSS overrides and this decision record. REA savings unmeasured (`savings=unknown`). Permissions: first-party repository and user-provided package only. No font binaries or private records included.

## Test / release contract

**This is not production evidence.** In the current design workspace, managed Chromium policy blocks opening both `file://` and `localhost` URLs; browser screenshot and signed-in visual verification cannot be claimed. The independently delivered companion design kit includes a click-through static HTML prototype, 125-key EN/FI/SV mappings, a contrast-pair validation and static CSS/JS checks.

Before merging: 5-gate CI as required, inspected desktop/tablet/mobile and FI/EN content, keyboard/focus, 200–400% text zoom, contrast in both modes, CV empty/upload/replace, Manual/Assisted/Automatic review, identity switch, offline AI behaviour, document export, disabled submission and genuine provider-ack transitions. Real automatic submission remains limited by existing employer-specific authorization. After approval, deploy only the exact reviewed SHA and collect release parity and two signed-in accounts. Never claim green mock tests prove employer transmission.

**Status:** design CSS READY FOR REVIEW; browser QA / user studies / approved production release NOT DONE.
