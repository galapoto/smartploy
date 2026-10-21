# SmartPloy — nationwide junior IT, data and planning discovery

21 October 2026 implementation checkpoint. This is the scope of the
**review branch** only, not a claim that these changes have reached the
old OVH website. Live old release still uses Cloudflare Access and
`smartploy.obumai.com`; `smartploy.komplyint.fi` needs new reviewed
OIDC release activation before visitors can use their ZITADEL sessions.

## User-facing core correction

- Default general browsing is **IT, data and planning**, with only
  **junior-labelled or experience-unspecified** vacancy titles visible;
  explicit senior-labelled titles are excluded by default. An
  unspecified level is NEVER claimed to be verified entry level.
- `All occupations` + `All experience levels` provides immediate
  escape hatches. Nothing is deleted from the original shared job
  repository. Browsing is independent of CV and per-account data.
- Every result is tagged from the **advertised title only** as
  `career_area=it_data|planning|other` and
  `title_experience=entry|senior|unspecified`. A driver title that
  mentions Python/data/phone apps in the **description** is no longer
  promoted to personalized IT recommendations from incidental
  keywords. Driver vacancies remain discoverable only when the user
  explicitly selects all occupations or targets those roles.
- The existing first-use IT starter sets role targets such as
  `Data Engineer`, `Junior Data Analyst`, `Suunnittelija`,
  `Projektikoordinaattori` and junior QA/business analysis. Its
  location setting is **blank = any location in Finland**; the old
  Helsinki/Espoo/Vantaa restriction is removed.
- Preserved original bilingual search and extended narrow
  English/Finnish role pairs for data engineer/data-insinööri,
  software developer/ohjelmistokehittäjä, IT support
  specialist/IT-tukihenkilö and project planner/projektisuunnittelija.
  A person explicitly requesting generic `Suunnittelija` can see
  compound advertised titles such as `Hankesuunnittelija`;
  no job body can fabricate a title match. Qualification scoring
  remains a **separate** approved-evidence check.

## Existing product code reused — inspect before reinventing

| Existing owned component | Actually reused | Not reused / cannot claim |
| --- | --- | --- |
| `smartploy/sources/public_ats.py` | Existing public Lever and Greenhouse GET adapters with exact approved host, bounded response, location filter, no employer POST | No new unlicensed web scraper |
| `smartploy/sources/public_ats_polling.py` and `worker_runtime.py` | Original worker schedules, source provenance, freshness and retire-on-complete checks | No replacement queue or fabricated vacancy counts |
| `smartploy/search_preferences.py`, `web/src/SearchSetup.tsx`, `SearchResultsPanel.tsx` | Original per-user setup, role scoring, general browsing, all-jobs storage | No CV or personal data supplied to external search engines |
| `scripts/configure_finland_ats_pilot.py` | Original root-protected private env staging, idempotence, refusal to override operator edits | No unreviewed source URLs in public env |
| `smartploy/auto_draft_shortlist.py` | Original explicit opt-in, title and freshness checks, approved profile, idempotent private workspace and owner guard | Never blindly apply for a job or infer employer permission |
| `obumai/obumbrowse` and `obumai/obumconnect` main | Repositories inspected for reuse; main had only `README.md` and `AGENTS.md` on this check | No demonstrable running ObumBrowse national crawling API or SaaS connector to copy. Must not invent one. |

**New from scratch:** small deterministic title taxonomy
`smartploy/career_scope.py`, limited bilingual/compound title
matching glue, default view filters, one reviewed seven-source JSON
portfolio, operator-only safe portfolio upgrade/rollback and regression
tests. No new dependency or third-party code copied. Time saved is
architectural (reused existing ATS/worker/auth/stores); no fabricated
hours/10x speed claim.

## Public sources validated (read-only, not yet active in production)

Original five Lever boards were:
`uprightproject`, `brightlyworks`, `netlight`, `rovio-2`,
`tsmg`. The last source publishes **driver/vehicle-testing roles**,
and is a contributor to the screenshot's unrelated driving jobs.

The reviewed IT-first pilot in
`config/finland_it_public_ats_portfolio.json` has **seven** employers:
the original first four Lever boards plus the official public
Greenhouse GET boards `oura`, `wolt`, `smartlyio`. Three Greenhouse
boards returned actual published-job JSON in a separate **read-only
public check on 2026-10-21**: Oura (80 published postings, four
advertised Finland locations), Wolt (203 / 21), Smartly (58 / 20).
Some Finnish listings are senior, so these figures are **not**
junior IT vacancy counts and may change before the next poll. The
read-only endpoint is Greenhouse's documented Job Board API:
https://docs.greenhouse.io/job-board .

The original `GreenhouseAdapter` can poll/retire locations and
skip null `internal_job_id` prospect-only postings. Candidate
source/current metadata is retained, and
`external_ai_forwarding_allowed=false` for all seven boards.

This is a **portfolio**, not a comprehensive jobs-in-Finland crawler:
it has a country match and 20 reviewed Finnish location terms.
Jobs that disclose only an unlisted municipality without a country
field may not pass the current conservative geographic filter.
We must expand safely after real source-health acceptance instead
of pretending to know every Finnish municipality.

## Production configuration (held until reviewed release)

**DO NOT run this from the old OVH checkout** at `fc94e78`.
After the reviewed integration source is checked out on OVH and
approved by the native ObumDelivery source gate, the original script
can safely stage the exact change:

```text
python3 scripts/configure_finland_ats_pilot.py --upgrade-it-portfolio
python3 scripts/configure_finland_ats_pilot.py --upgrade-it-portfolio --apply
```

The dry-run must show `source_count=7` and
`private_env=change_ready` or `unchanged`; the apply operates
only on `SMARTPLOY_PUBLIC_ATS_SOURCES_JSON` in private env.
It refuses any unknown operator changes or a configured source file,
keeps the current rotated database credential untouched, and
does not poll/submit/start Docker. After actual source registration
and live acceptance, rollback is the same existing operator tool:
`--rollback-it-portfolio --apply`. This restores the reviewed
five-source selection only if it exactly matches the seven-source
portfolio. The original five-source registry is preserved.

On live acceptance inspect source-health individually (not just the
dashboard total); require fresh GET success, stable source IDs,
correct location/role semantics and new actual vacancy rows. Keep
global unattended employer submission disabled.

## Much broader nationwide coverage requires official access

### Työmarkkinatori / Job Market Finland — highest priority source

The existing `smartploy/sources/jobmarket_finland.py` already
implements the official KEHA **P67 v2** job-search adapter, but the
owner's last shown private production env has
`JOBMARKET_FINLAND_API_ENABLED=false` and an empty subscription key.
Access requires a suitable Finnish organization, acceptance of KEHA
terms, a **käyttöönottoilmoitus** and KEHA's secure credentials/IP
allowlisting. Public instructions and application form are at:

https://tyomarkkinatori.fi/ohjeet-ja-tuki/rajapinnat/tyopaikkailmoitusten-rajapinnat/hakurajapinnan-kuvaus-ja-ohjeistus

The approval belongs to the legitimate applicant organization.
The user/operator must request KEHA access, complete the QA test
phase, and obtain separate production credentials. Never paste a
subscription key into GitHub, chat or job logs. This official national
feed is more relevant for widespread geographic coverage than
inventing thousands of employer board names.

### Duunitori and LinkedIn

Duunitori and LinkedIn currently have **external search links**
in the app as a separate handoff. Neither is counted in the
original API's `available_count`, and no listings from those
websites may be promoted into unattended draft/submit workflows merely
by following the link. Implement a dedicated adapter only after
the provider permits the intended automated data reuse, and preserve
per-post provenance, canonical identity and current availability.

LinkedIn's job integration requires applicable provider/partner
permissions; a user login is not automatically a data-ingestion
license. Uncontrolled scraping or bypassing logins is not a substitute
for legitimate job search integrations.

## Release truth and remaining gates

- **Done in source:** classifier, general junior/planning browse, safe
  external search handoffs, seven-board portfolio, staged private
  settings helper, Finland + bilingual tests.
- **CI:** see the exact-head GitHub Action for this branch. The
  synthetic tests are NOT evidence of a live OVH poll.
- **Not deployed:** newer first-party OIDC/AutoApply and 7-board
  configuration. No authenticated, source-backed draft confirmed
  on `smartploy.komplyint.fi`.
- **Blocked:** native ObumDelivery approval, integration PR review,
  exact-SHA OVH migration, two-account ZITADEL login, KEHA source
  access, provider-specific actual employer-submit authorization.
- **Next proof:** source counts by provider at the new running SHA,
  48-hour freshness, zero non-IT recommendations for focused users,
  per-account opted-in job-to-private-draft, and explicit
  `actually_submitted=0` until real provider acknowledgment.
