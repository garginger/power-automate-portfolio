# Reusable patterns

These patterns recur across the flows in this repo. Each one exists because the simpler approach failed in production or in review.

## 1. Try / Catch with a run link

Wrap the main path in a `Try` scope. Add a sibling `Catch` scope that runs after `Try` **has failed** or **has timed out**. Inside Catch:

- **Find the failing action.** Run a Filter array on `result('Try')` for status `Failed` or `TimedOut`. Don't use `result('Try')[0]`, because index 0 is often a *skipped* action with no error.
- **Report the error safely.** Read the message with `coalesce(first(body('Filter_array'))?['error']?['message'], 'No error message returned')`, so a missing error object can't make the error handler itself fail.
- **Link to the run** so whoever gets the alert lands right on it:

```text
concat('https://make.powerautomate.com/environments/', workflow()?['tags']?['environmentName'],
       '/flows/', workflow()?['name'], '/runs/', workflow()?['run']?['name'])
```

- **End with Terminate: Failed.** Without it, a handled failure shows as *Succeeded* in run history.

Used in: [PD Approvals](../flows/professional-development-approvals/), [Copy to Tracker](../flows/pd-approvals-copy-to-tracker/), [Emerging Leaders](../flows/emerging-leaders-application/), and per item in [Promo Archival](../flows/promo-expiration-archival/).

## 2. Approvals with reminders and a clean expiry

**Start and wait for an approval** can't send reminders, and it waits up to 30 days before failing. Instead:

```text
Create an approval                      (one request, so one item in the approver's inbox)
Do until  responded OR waits >= 4       (Change limits: count 6-10, timeout P14D-P15D; the default is PT1H)
  Wait for an approval                  (action timeout P3D)
  ├─ on Succeeded → save outcome, comments, date to variables
  └─ on TimedOut  → increment waits; if waits < 4, send a reminder
After the loop: if no outcome → Needs Attention, notify, Terminate: Succeeded
```

- **Reminders and expiry.** Reminders go out on days 3, 6 and 9, with escalation CCs on the later ones, and the request expires on day 12. Two stages back to back still fit under the 30-day run limit.
- **Variables instead of action references.** Downstream logic reads variables, never the action inside the loop.
- **Leave *has failed* unchecked** on the timeout path, so real errors still reach Catch.
- **Expiry ends as *Succeeded*.** No response is a business outcome, not an IT failure.

## 3. SharePoint write-backs with `validateUpdateListItem`

Use this when a flow must update a few columns without resending every required field, or when the item's permissions are broken.

```text
Compose (object):  { "formValues": [ { "FieldName": "Internal_x0020_Name", "FieldValue": "@{...}" } ],
                     "bNewDocumentUpdate": false }
Send an HTTP request to SharePoint:  POST _api/web/lists(guid'...')/items(ID)/ValidateUpdateListItem
                                     Accept / Content-Type: application/json;odata=nometadata
                                     Body: outputs('Compose')
Condition: contains(string(body('HTTP')), '"HasException":true')  → alert
```

- **Build the body in a Compose typed as an object.** User text with quotes, apostrophes or line breaks is then escaped correctly.
- **Check `HasException`, not the status code.** The endpoint returns **200 even when a field fails**.
- **Use internal names,** which SharePoint truncates at 32 characters. Look each one up instead of guessing.
- **For a lightweight stamp,** a `MERGE` (`X-HTTP-Method: MERGE`, `IF-MATCH: *`) with a plain JSON body also works.

## 4. Idempotent change-driven triggers

A *created or modified* trigger re-fires on its own writes and on unrelated edits. Four layers prevent double processing:

1. **Trigger conditions** filter on the target state and a "done" flag, for example `Status = Approved` and `TrackerCopied ≠ true`.
2. **Trigger concurrency set to 1,** so runs queue instead of racing.
3. **A recheck at the top of the run:** re-read the item and exit if it's already stamped.
4. **A natural-key lookup before creating** (`PDSourceID eq {ID}`). If a previous run created the target but failed to stamp the source, the next run links to the existing copy instead of making a duplicate.

## 5. Microsoft Graph paging

```text
nextLink = 'https://graph.microsoft.com/v1.0/users?$select=...&$expand=manager(...)&$top=999'
Do until empty(nextLink)
  HTTP GET variables('nextLink')       ← never the hard-coded first URL
  Compose: union(variables('all'), body(...)?['value'])
  Set all = outputs('Compose')         ← Set variable can't reference itself
  Set nextLink = coalesce(body(...)?['@odata.nextLink'], '')
```

`$expand` caps each page at 100 results no matter what `$top` says.

## 6. Failure digests in loops

Inside an Apply to each, a per-item Try/Catch appends a line to an array variable when that item fails. After the loop, one email goes out only if the array isn't empty.

- **Set the loop's concurrency to 1.** Parallel iterations appending to the same variable lose entries, and an incomplete digest that *looks* complete is worse than none.

## 7. HTML email built in Compose

The modern designer's email body uses a rich-text editor (Lexical) that can't round-trip tables or styled `div`s, and that rejects long bodies with many nested-quote expressions.

- **Build the HTML in a Compose,** which has a plain expression field, with inline `@{...}` expressions and inline CSS.
- **Pass a single `Outputs` token** to the email body.

Used in: [Emergency Alerts](../flows/emergency-alert-notification/), [Monthly Report](../flows/branch-activity-report/).

## 8. Item-level confidentiality through REST

```text
POST .../items(ID)/breakroleinheritance(copyRoleAssignments=false,clearSubscopes=true)
POST .../items(ID)/roleassignments/addroleassignment(principalid={service account},roledefid={Full Control})
POST .../items(ID)/roleassignments/addroleassignment(principalid={reviewers group},roledefid={Edit})
```

- **Grant the service account explicitly.** Otherwise the flow's later write-backs are denied once inheritance is broken.
- **List-level "read/edit only your own items"** covers the seconds before the lock.
- **If the lock fails, stop the flow before anything sensitive goes out.**
- **Item-level settings don't restrict Manage Lists.** Anyone with Manage Lists or higher bypasses them, so keep that permission tight.
