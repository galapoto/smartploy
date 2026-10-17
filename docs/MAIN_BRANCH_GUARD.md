# SmartPloy main branch governance — owner setup and independent verification

**State observed on 16 October 2026:** `galapoto/smartploy` is a **public**
GitHub repository; `main.protected=false`; the repository ruleset list was
empty; integrated release PR [#137](https://github.com/galapoto/smartploy/pull/137)
was **DRAFT**, with zero submitted human reviews, and the current PR-head CI
passed. These facts do **not** imply that unreviewed code was merged or that
OVH production was deployed.

## Native GitHub protection — repository admin must configure and verify

In [repository Settings](https://github.com/galapoto/smartploy/settings/rules),
open **Rules > Rulesets** (or **Branches > Branch protection rules** if rulesets
are unavailable). Choose **New branch ruleset** for **`main` only**. Confirm
the rule applies to the default branch; do not inadvertently match all branches,
including review branches. Verify GitHub's plan-specific ruleset capabilities
**before** creating an enforcing rule. Do not buy GitHub upgrades without
owner approval.

Set the rule to **Active** (not merely Evaluate / Disabled), and configure:

1. **Restrict deletion** and **block force pushes** to `main`.
2. **Require a pull request before merging**, with **at least one approving
   independent reviewer** when supported. Dismiss stale approvals on new
   commits; do not treat author self-approval or bot CI as independent review.
3. **Require status checks to pass** for the exact, up-to-date merge candidate.
   If GitHub can discover check names, select the five *actually emitted*
   jobs from the successful Smartploy CI workflow rather than typing guesses:
   `test`, `web`, `browser`, `deploy-stack`, and
   `Exact-checkout review receipt (not release approval)`.
   Check app/source must be **GitHub Actions**, where selectable.
4. **Require branch to be up to date before merging** when available. A
   stale green PR run is not evidence for a changed `main`.
5. Restrict bypasses, force pushes and administrator exceptions where
   permitted; preserve a documented owner recovery path.

Do **not** create an active rule requiring checks absent from the workflow:
that could deadlock releases. Do not allow a branch rule to convert a draft PR
into an approved release. Do not enable GitHub auto-merge or any automatic
OVH deployment. Record any plan-enforcement limitation in [issue #138](
https://github.com/galapoto/smartploy/issues/138) and keep the documented
manual review/approval gate until enforceable native rules are configured.

## Post-setup proof (read-only, no test merge)

The administrator should record these **separately**, ideally with redacted
screenshots or GitHub API output, in issue #138:

- Exact ruleset/rule name, `main` target, Active enforcement, restrictions,
  required approval count and required check names; screenshot contains no secrets.
- GitHub `branches/main` protection information **or** equivalent active
  ruleset proof. A `403 Resource not accessible by integration` response is
  **inconclusive**, not proof of enabled protection.
- Actual check names from a fresh head CI run, successful exact source SHA,
  and review receipt's tested merge SHA and tree equality.
- Draft [#137](https://github.com/galapoto/smartploy/pull/137) remains unmerged
  and can be reviewed without any production or employer action.
- A branch rule shown as "Evaluate", "Disabled" or a ruleset list that is empty
  is **not** enforcement.

When `main` is protected, request a separate independent audit of the
integrated 35-file PR. Review the OIDC/Cloudflare identity boundary, cookie
CSRF, account switching, tenant-scoped saved jobs, privileged ATS mutations,
the exact-read frontend, Docker runtime policy, database migrations, and the
CI receipt; log concrete issues as blocking PR review comments. Never have
the PR author impersonate a distinct reviewer. Machine code checks do not
satisfy the human review requirement.

## Hard release hold

Keep these distinct:

- **Automated verification:** green PR CI and read-only evidence, not a review.
- **Human release decision:** reviewed source or explicitly documented owner
  exception, then authorized merge and green **post-merge main-push CI**.
- **Deployment:** owner-approved pinned full SHA, pre-deploy backup and restore
  plan, protected ingress, image/DB checks on OVH.
- **Real-world validation:** [live two-account A1–A7 checks](https://github.com/galapoto/smartploy/issues/91)
  and separately approved Obum Identity migration.

Until each gate is satisfied, do not alter Cloudflare Access, deploy candidate
code, assert real-login acceptance, or submit job applications.
