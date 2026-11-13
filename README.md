# Power Automate Portfolio

Production Power Automate flows I designed and built as the Automation & AI Solutions Specialist at a regulated credit union (FFIEC / NCUA / GLBA). They're published here as sanitized reference definitions, with the design reasoning, the bugs caught along the way, and the checks I run on them.

The newest entry, [Email Due Dates](flows/email-due-date-extractor/), differs on both points. It's a tested build whose pilot is still pending, not a production flow yet, and its definition is sanitized from a real solution export.

**Curt Criss** · Power Platform · Microsoft 365 administration · Entra ID / hybrid AD

## The flows

| Flow | What it does | Worth a look for |
|---|---|---|
| [Professional Development Approvals](flows/professional-development-approvals/) | Two-stage approval routing with a $500 threshold | Reminders on days 3/6/9 and a clean expiry on day 12 in place of a 30-day silent wait. Trigger-level filtering of on-behalf entries. Try/Catch. |
| [Copy to Development Tracker](flows/pd-approvals-copy-to-tracker/) | One-way push of approved requests to another team's list | Idempotency in three layers. A REST `MERGE` stamp. No cross-site permissions granted. |
| [Emerging Leaders Application](flows/emerging-leaders-application/) | Confidential application with two recommendations | An item lock via SharePoint REST within seconds of submission. Parallel recommendation branches with independent clocks. `validateUpdateListItem` write-backs with `HasException` checks. Secured run history. |
| [AD Hygiene: Disabled Manager Report](flows/disabled-manager-report/) | Weekly report of staff whose manager account is disabled | Microsoft Graph `$expand` with `nextLink` paging. Emails only when there's something to fix. |
| [Referral Routing](flows/referral-routing/) | Routes branch referrals to the right team | A nine-branch Switch replaced by a routing table. Alerts on unmatched routes. Branch openings become a toggle. |
| [Monthly Team Activity Report](flows/branch-activity-report/) | Monthly per-person and per-category activity email | Multi-select flattening, an `xpath` sum, and a 16-column matrix. An AI narrative tested and **rejected** for fabricating figures. |
| [Promo Expiration Archival](flows/promo-expiration-archival/) | Daily archive of expired member-facing promotions | An off-by-one date fix, a per-item Try/Catch, and a single failure digest. |
| [Emergency Alert Notification](flows/emergency-alert-notification/) | Notifies responders when staff raise an emergency | A confirmation that only follows a successful send. A failure escalation path. The Compose-HTML workaround. |
| [Email Due Dates](flows/email-due-date-extractor/) | Turns due dates buried in one person's email into calendar events, twice each weekday | One AI prompt call per thread, with deterministic actions around it. Three layers of dedupe on a SharePoint ledger. A watermark that only moves on success. **Tested build, pilot pending,** with its full [build guide](flows/email-due-date-extractor/build-guide.md) and [prompt](flows/email-due-date-extractor/prompt.md). |

## Patterns across the flows

| | PD Approvals | Copy | Emerging Leaders | AD Hygiene | Routing | Report | Archival | Alerts | Due Dates |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| Try / Catch scopes | ✓ | ✓ | ✓ | | | | ✓ | | ✓ |
| Approvals with reminders + expiry | ✓ | | ✓ | | | | | | |
| SharePoint REST | | ✓ | ✓ | | | | | | |
| Idempotent triggers | | ✓ | | | | | | | |
| Item-level security | | | ✓ | | | | | | |
| Microsoft Graph | | | | ✓ | | | | | ✓ |
| Configuration as data | | | | | ✓ | ✓ | | | ✓ |
| Failure alerting / digest | ✓ | ✓ | ✓ | | ✓ | | ✓ | ✓ | ✓ |
| Environment variables | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| AI judgment, deterministic actions | | | | | | | | | ✓ |
| Dedupe ledger + watermark | | | | | | | | | ✓ |

Each pattern is written up, with expressions, in [docs/patterns.md](docs/patterns.md).

## What's in each folder

```text
flows/<flow-name>/
├── README.md                        problem, design, decisions, lessons, configuration, action outline
├── definition.json                  workflow definition in solution-export format
└── deploymentSettings.sample.json   environment variable + connection reference template for pac
```

`definition.json` has the same shape as a solution's `Workflows/*.json`:

- **`properties.definition`** is the Logic Apps workflow definition: triggers, actions, `runAfter`, expressions.
- **`properties.connectionReferences`** names the connection references.
- **Environment variables** appear as `parameters`, referenced like `@parameters('PD Requests List (plb_PDRequestsList)')`.

Every README ends with a generated action tree, so you can scan a flow's structure without opening the JSON.

Email Due Dates has two more files: `build-guide.md`, the full step-by-step build, and `prompt.md`, its AI prompt.

## About these definitions

**Eight of the nine are reference definitions, not raw exports.** Each of those was rebuilt from the build specification and design reviews of the production flow:

- **What mirrors production:** action names, structure, expressions, run-after wiring, timeouts and security settings.
- **What was replaced:** organization names, people, site URLs, list IDs and email addresses, all swapped for Contoso placeholders. Hard-coded references became environment variables.
- **Simplifications:** where a detail was simplified or assumed, the flow's README says so under *Reconstruction notes*.

**Email Due Dates is the ninth.** Its `definition.json` is the workflow JSON from a solution export of the tested build, with names and identifiers replaced. Its README lists every change under [*Sanitization notes*](flows/email-due-date-extractor/#sanitization-notes).

The definitions pass this repo's structural and sanitization checks, but they **haven't been import-tested yet**. Importing them into a Dataverse developer environment, and replacing the JSON with `pac solution unpack` source, is next on the [roadmap](docs/alm.md#roadmap).

## Quality checks

| Check | What it catches |
|---|---|
| [`scripts/validate_definitions.py`](scripts/validate_definitions.py) | `runAfter` pointing outside its scope, references to missing actions, uninitialized variables, undeclared environment variables, duplicate names, cycles. It also flags a "has timed out" branch hung off an action that can't time out, the [real bug](flows/emerging-leaders-application/#lessons-from-the-build) a pre-go-live review caught. |
| [`scripts/check_sanitization.py`](scripts/check_sanitization.py) | Non-placeholder emails, hosts and GUIDs, token-shaped strings, and a private deny-list kept out of the repo ([details](docs/sanitization.md)). |
| [CI workflow](.github/workflows/validate.yml) | Runs both scripts, a JSON parse check and gitleaks on every push. |

```bash
python3 scripts/validate_definitions.py
python3 scripts/check_sanitization.py .
```

## Working in a regulated environment

A few practices shape every flow here:

- **Service-account ownership.** Production flows run under a dedicated automation account, with the builder as co-owner, so nothing depends on one person's account.
- **Least privilege.** Business teams aren't granted access to the IT automation site. Data is pushed to them instead. Confidential items are locked per item.
- **Run history is data, too.** Approval responses and write-back payloads that carry sensitive text use secure inputs and outputs.
- **Fail loudly, not silently.** Every flow that can fail in a way a person needs to know about sends an alert with a run link. Clean runs send nothing.
- **Change control.** Changes are built in a copy, tested with shortened timeouts, reviewed against the spec, then cut over, with the old flow kept as a rollback.

## Docs

- [Reusable patterns](docs/patterns.md)
- [ALM: environment variables, connection references, deployment](docs/alm.md)
- [Sanitization](docs/sanitization.md)
