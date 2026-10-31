# SP93 — Visible, sidebar-first CV → Manual / Assisted / Automatic

## Production finding and user requirement (31 October 2026)
The user deployed `f43fe423aceef75e1d4ca134f19a43e5d6529c3a`
with `SmartPloy release evidence: PASS`. Despite this, they could
not find the Manual, Assisted or Automated flow. They asked to retain
the previous useful UI, **keep the current sidebar**, and adopt only
the good design principles in Komplyint's production design guide.

Source inspection identified **two discoverability defects**:
- `StartChoices.tsx` rendered *zero* method cards until `cv.present`
  was true; the user could not even preview the paths on the first visit.
- `App.tsx` returned a standalone `setup-landing` while
  `preferences.completed` was false and page was the dashboard,
  removing the normal sidebar for new signed-in users.

The guided `ApplicationJourney.tsx` also hid its mode grid entirely
when no CV existed. In the existing CSS, StartChoices' default
grid had only two columns, placing the **third Automatic option on a
separate row** at common desktop sizes.

## Implemented behaviour
- Every signed-in user, including one who has not configured search
  preferences, sees the **existing navigation sidebar** and an
  immediately visible CV-first application journey on Start here.
- All three Manual, Assisted, Automatic (AutoApply) options **render
  for every CV state**. Before a CV is saved, they are clearly
  labelled but disabled: seeing capabilities is not selecting one.
- Upload or create a CV in Step 1. Existing `onCVUpload`,
  `MasterCVEditor.onSaved` and `startApplyFlow` continue to
  transition to Apply with no preselected method.
- Step 2 buttons become active when the account has an uploaded/saved
  CV. Selecting one shows existing CV-matched jobs and the original
  mode-specific actions and review gates.
- Job browsing without a CV and optional search preferences remain
  available, with optional settings in an expandable dashboard section
  or the unchanged Advanced settings sidebar route.
- Sidebar's existing ten destinations are retained, with a small
  readable hint beneath Apply for jobs.
- The established app header, job cards, saved applications, CV editor,
  cover-letter editor and worker services are unchanged.
- No employer submission or external action is authorized by
  selecting a mode, uploading a CV or previewing a locked card.
  Applicant-specific CV consent and employer-specific send rights stay
  enforced by the original backend.

## Komplyint design-guide principles used
Source: `Komplyint_Website_Production_Guide_2026-10-30.pdf`,
especially pages 8–9 and 21. Adapt:
- coherent type hierarchy, clearer functional labels and readable
  explanation text, without swapping in Komplyint's branding fonts;
- stable spacing, grid discipline and three-card alignment only where
  the cards remain legible, with a single-column mobile reflow;
- buttons with meaningful states, legible disabled previews and
  keyboard focus treatment;
- minimal borders/shadows, understandable empty/locked states,
  no arbitrary fixed card clipping, and reduced motion support.

Do **not** copy Komplyint's forest-green/crimson/charcoal palette,
marketing navigation, logos or corporate typography. SmartPloy keeps
its ink/sea/cyan, light application-workspace identity and existing
sidebar navigation.

## Test and release acceptance
- React tests assert **three visible preview modes even without a CV**
  and **no accidental mode selection**, then unlock and select after
  a saved CV; check the same behaviour from Apply and Start here.
- React App tests assert the sidebar exists with incomplete preferences,
  both before and after entering Apply, and verify no employer-facing
  mutation is triggered merely by choosing a mode.
- Require web build/test, backend regression, browser acceptance,
  isolated Compose smoke and exact-checkout CI PASS before merge.
- Production release requires the exact merged Git SHA, OIDC deploy,
  `release-evidence.sh --online` PASS and public web/API release
  parity. CI cannot substitute for authenticated operator visual
  acceptance after the deploy.

This change is deliberately a **discoverability and interaction fix**,
not a new AutoApply provider or claim of unrestricted fully
unattended employer submissions.
