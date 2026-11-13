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

Used in: [Promo Archival](../flows/promo-expiration-archival/), and in [Email Due Dates](../flows/email-due-date-extractor/) in a lighter form: one Append to string that runs after the per-thread scope *has failed* or *has timed out*. There, a failed thread would otherwise freeze the watermark (pattern 11).

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

## 9. AI judges, the flow acts

Use one prompt call for the judgment a rule can't make, and keep every side effect in flow logic.

```text
Per thread:
  Compose the inputs       (owner profile, thread text, rows already tracked)
  Run a prompt             → strict JSON: [{ action, existingItemId, title, dueDate, confidence, ... }]
  Compose + Parse JSON     (strip code fences, loose schema)
  Apply to each item
    deterministic guards   (dedupe key lookup, confidence threshold, row status)
    Switch on action       → create / update / nothing
```

- **Ask for decisions, not actions.** The prompt returns `create` or `update` plus fields. It never calls anything.
- **Show the model what's already tracked,** with row IDs, and have it return the ID it means. Then check that ID against the rows that were sent: `equals(item()?['ID'], coalesce(items('For_Each_Item')?['existingItemId'], -1))`.
- **Make "not sure" an outcome.** A confidence score, compared with a threshold held in config, sends doubtful items to a `Maybe` row instead of the calendar.
- **Don't trust the response's shape.** Strip code fences, require only the essential fields in Parse JSON, and clean any model text before it goes into a JSON body: `replace()` out quotes, backslashes, `%0A`, `%0D` and `%09`.
- **Give dates an anchor.** Put the weekday in every timestamp the model reads, and say which timestamp relative dates resolve against.

That split is what makes the result testable. The counter-example is the [Monthly Report](../flows/branch-activity-report/), where an AI narrative was rejected for inventing figures.

Used in: [Email Due Dates](../flows/email-due-date-extractor/) ([prompt](../flows/email-due-date-extractor/prompt.md)).

## 10. A ledger list for dedupe

A calendar can't say whether the flow already created an event, or tell "never created" from "deleted on purpose." When the target system has no key to look up, keep a ledger: one list row per decision.

- **Write a row for every outcome,** including the ones that created nothing (`Maybe`).
- **Check a computed key before every create.** Strip apostrophes so the key is safe inside an OData filter (`DedupeKey eq '...'`), and index the column:

```text
toLower(concat(outputs('Item_Due_Date'), '|', take(replace(replace(replace(replace(outputs('Item_Title_Safe'), ' ', ''), '''', ''), '.', ''), ',', ''), 30)))
```

- **Never delete rows. Use a tombstone status.** When the target is gone, mark the row (`EventMissing`), keep counting it as tracked, and exclude it from updates. That's what stops a deleted event from coming back.
- **Re-read inside the loop** when two iterations in one run can hit the same item. A read before the loop can't see the rows the loop just wrote.
- **Store dates you compare as `yyyy-MM-dd` text.** They sort and compare correctly as strings.

This is layer 4 of pattern 4, the natural-key lookup, for a target with no natural key.

Used in: [Email Due Dates](../flows/email-due-date-extractor/).

## 11. A watermark that only moves on success

For a scheduled flow that reads "everything since last time":

```text
Init varRunStartUtc = utcNow('yyyy-MM-ddTHH:mm:ssZ')        ← before anything is read
Try
  Get Config                                                 ← LastRunUtc is a column on a list row
  GET ...?$filter=receivedDateTime ge formatDateTime(LastRunUtc, 'yyyy-MM-ddTHH:mm:ssZ')
  ...process...
  Update Config: LastRunUtc = varRunStartUtc                 ← the last action in Try
Catch (Try has failed / has timed out)  → alert, Terminate: Failed
```

- **Save the run's start time, not its end,** so anything that arrives mid-run is read next time.
- **Make the save the last action in Try.** A failed run then rereads the same window.
- **A reread has to be harmless,** so the processing must be idempotent. Pattern 10 does that here.
- **Normalize the format on the way in.** With `formatDateTime()` around the stored value, a watermark saved in another date shape doesn't break the filter.
- **Don't let one bad item hold the watermark hostage.** Without a per-item scope (pattern 6), the same item fails every run and nothing after it is ever read.
- **Keep it in a list row,** where it can be reset by hand. Rewinding it is how a go-live replays the test window.

Used in: [Email Due Dates](../flows/email-due-date-extractor/).

## 12. Graph through the Outlook connector

The Office 365 Outlook connector's **Send an HTTP request** calls Graph as the connection's user. Pattern 5 does the same through Office 365 Users for directory reads. The Outlook connector reaches mail and calendar, and it can write.

```text
GET   https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages?$filter=...&$select=...&$top=500
GET   https://graph.microsoft.com/v1.0/me/messages?$filter=conversationId eq '...'&$select=...,uniqueBody,webLink
        CustomHeader1   Prefer: outlook.body-content-type="text"
POST  https://graph.microsoft.com/v1.0/me/events            Body: outputs('Event_Payload')
PATCH https://graph.microsoft.com/v1.0/me/events/{id}       Body: outputs('Event_Payload')
```

- **The URI has to start with `/me`** and use a segment the connector supports: `messages`, `mailFolders`, `events`, `calendar`, `calendars` or `outlook`.
- **The connection is the scope.** `/me` is whoever owns the connection, so a flow like this runs under the mailbox owner's connections, not a service account's.
- **Wrap the `$filter` value in `encodeUriComponent()`.** Inside an expression, a literal single quote is written as two.
- **`uniqueBody` plus the text `Prefer` header** returns only each message's new text, as plain text. That's far fewer tokens than HTML with the quoted history under it.
- **Build JSON bodies in a Compose** and pass its output. A number token goes in without quotes.
- **`$top` isn't paging.** Past the cap, follow `@odata.nextLink` as in pattern 5.

Used in: [Email Due Dates](../flows/email-due-date-extractor/).

## 13. Only a 404 means gone

After a PATCH to something a person may have deleted:

```text
Scope Try_Patch
  PATCH .../me/events/{id}
Condition Patch_Worked       (runs after Try_Patch: is successful, has failed)
  first(result('Try_Patch'))?['status']  equals  Succeeded         → log the update
Condition Event_Gone         (a sibling below Patch_Worked)
  outputs('Update_Calendar_Event')?['statusCode']  equals  404     → tombstone the row
```

- **Treat only a 404 as "deleted."** Throttling, an outage and a bad payload are failures too, and tombstoning on any of them would abandon a live item for good.
- **Leave every other failure alone,** so the next run tries again.
- **A failure handled this way doesn't fail the run,** because the actions after it succeed.

Used in: [Email Due Dates](../flows/email-due-date-extractor/).

## 14. Flatten a branch to stay under the nesting limit

Power Automate won't save a flow whose actions nest more than 8 levels deep. Scopes, loops, switches and conditions all count, and a Try scope around a loop with a per-item scope inside it uses three levels before the real logic starts.

- **Turn a nested "else if" into a sibling.** `Event_Gone` in pattern 13 belongs, logically, inside `Patch_Worked → False`. As a sibling condition below it, with its own test, it behaves the same and sits one level higher.
- **Check that the sibling does nothing on the other path.** Here a successful PATCH returns 200, so the 404 test is false.
- **Precompute in Composes** above the branch (`Is_Confident`, `Event_Payload`), so each condition is one test instead of a nest of them.
- **Count the levels before building the deepest branch,** not after the designer refuses to save.

Used in: [Email Due Dates](../flows/email-due-date-extractor/).
