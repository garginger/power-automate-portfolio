# Email Due Dates (EDD): Build Guide

The full step-by-step build for the [Email Due Dates flow](README.md). Every step gives the exact action type, the name to rename it to, the HTTP method where there is one, what goes in each field, and whether the value is typed text, dynamic content, an **fx** expression or pasted JSON.

**Status: tested build, pilot pending.** Phase 1 below was run in the builder's own mailbox against a test calendar, and all ten of its cases passed. Phases 2 and 3 haven't happened yet.

## Reading this guide

- **"The requester"** is the staff member whose mailbox the flow reads. **"You"** are the builder. The prompt and the Config list call the requester the *owner*.
- **EDD** stands for Email Due Dates. It prefixes the lists, the prompt, the solution and the flow.
- **fx** means: click into the field, open the expression editor, and paste the expression. fx expressions are shown as you paste them, with no leading `@`. Filter array's advanced mode is the exception: those are shown with their `@`, because that's how the field takes them.
- **Rename every action exactly as shown in quotes.** The expressions reference those names, and spaces become underscores (for example, `Get Config` is referenced as `body('Get_Config')`). Rename an action before you write the expressions that reference it.
- **The guide and [`definition.json`](definition.json).** The guide builds the flow the way the tested build was made: the site and lists are picked in the designer, and the alert recipient is typed in. The published definition swaps those for environment variables and has exactly one connection reference per connector (see [Configuration](README.md#configuration) and [Sanitization notes](README.md#sanitization-notes) in the README). Action names, structure and expressions are the same. A few `GET` actions in the export also carry a Content-Type of `application/json` that this guide doesn't ask for. It has no effect on a `GET`.

## Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Step 1: Create the SharePoint lists](#step-1-create-the-sharepoint-lists)
- [Step 2: Build the AI prompt](#step-2-build-the-ai-prompt)
- [Step 3: One-time Outlook setup](#step-3-one-time-outlook-setup)
- [Step 4: Flow shell: trigger, variables, settings](#step-4-flow-shell-trigger-variables-settings)
- [Step 5: Get new mail, filter it, group by thread](#step-5-get-new-mail-filter-it-group-by-thread)
- [Step 6: Loop each thread and call the prompt](#step-6-loop-each-thread-and-call-the-prompt)
- [Step 7: Create, update or skip each item](#step-7-create-update-or-skip-each-item)
- [Step 8: Summary, watermark and error handling](#step-8-summary-watermark-and-error-handling)
- [Testing and rollout](#testing-and-rollout)
- [Changing behavior later](#changing-behavior-later)
- [Troubleshooting](#troubleshooting)
- [Sources](#sources)

## Overview

A scheduled cloud flow runs at 7:05 AM and 4:05 PM each weekday under the requester's own connections. It reads their new Inbox and Sent mail, uses an AI prompt to find items that are theirs and have a due date, and creates Outlook events with reminders. There are no approvals and no duplicates.

| Requirement | How this build meets it |
| --- | --- |
| Automatic, no approval step | Events are created directly. A Teams summary after each run is for visibility only. |
| No duplicate events | The prompt sees items already tracked. A dedupe key is checked before every create. Events the requester deletes are never recreated. |
| Event on the due date, heads-up 1+ day ahead | Small items: reminder 1 day before (1440 min). Big items: 3 days before (4320 min). Both live in the Config list. |
| Group requests count as the requester's for now | `CountGroupRequests = Yes` in the Config list. Flip it to No anytime. |
| Some senders always or never count | A Sender Rules list, empty at launch. Add rows anytime, no flow edit needed. |
| Their mailbox, their account | All connections are the requester's, so every Graph call to `/me` is their mailbox and calendar. |

**Why a flow with a prompt, not an agent.** The AI judgment (is this the requester's, what is the date) happens inside one prompt call per email thread. Everything that creates, updates or skips an event is fixed flow logic, which is what makes "no duplicates" testable.

**One run, twice each weekday.** Each thread gets one AI call. Only new, confident, dated items become events. Date changes move the existing event, and everything else is logged as Maybe and listed in the Teams summary. The [architecture diagram](README.md#architecture) in the README shows one run end to end.

## Prerequisites

Settle licensing and credits before you build. The AI prompt action makes this a premium flow, and prompts now run on Copilot Credits.

**Licensing and credits**

- **Premium flow.** Microsoft's AI Builder licensing page says any flow using an AI Builder action is premium and needs Power Automate Premium licensing. The requester will be the primary owner, so they need a Power Automate Premium license. ([source](https://learn.microsoft.com/en-ie/ai-builder/administer-licensing))
- **Credits.** The AI Builder credits that came with premium licenses reached end of life on November 1, 2026. Credits already granted are honored only to the end of the contract term. After that, prompts draw on Copilot Credits unless the organization still has an active AI Builder add-on. Confirm the target environment has Copilot Credits allocated in the Power Platform admin center. ([source](https://learn.microsoft.com/ai-builder/endofaibcredits))
- **Model choice.** Premium LLM models cost several times more credits per call than standard ones. Start on a standard model and move up only if quality falls short.

**Accounts and ownership**

- Build the flow inside a **solution** named `EDD Email Due Dates` (EDD = Email Due Dates), so connections are connection references you can swap at go-live.
- Build and test with **your own** connections against your own mailbox, with the Config list pointing at you. At go-live, the requester signs into new connections, you point the connection references at theirs, and you make them the primary owner. You stay a co-owner for support.
- The Office 365 Outlook connector's **Send an HTTP request** action calls Graph as the connection's user. It supports `/me` with the `messages`, `mailFolders`, `events`, `calendar`, `calendars` and `outlook` segments, which covers every call here. ([source](https://dev.to/kkazala/invoke-an-http-request-without-a-premium-license-connectors-summary-4pmd))

**Where things live**

- **SharePoint:** three lists on a site where only the requester and you have access (break inheritance on each list). The Action Items list holds titles and short quotes from the requester's email, so treat it as sensitive.
- **Outlook:** a calendar named `Due Dates (Test)` in the owner's mailbox for the test phase. During your build, create it in your own mailbox. Before the requester's test week, create it in theirs.
- **Teams:** used for the run summary to the requester and failure alerts to you. Using Teams instead of email keeps the flow from reading its own messages in Sent Items.

**Governance:** this sends email content to an AI Builder prompt inside the organization's Microsoft tenant. Log it against the organization's AI use policy like any other AI-assisted process. The prompt also tells the model to mask account numbers and member personal data in anything it writes back. Co-owners can open run history, which shows the email text each action read. After Phase 2, turn on Secure outputs (action → Settings) for the actions that carry the requester's mail, 6.2 through 6.5 and 6.10 through 6.12, so nobody browsing a run sees it by default. Turn them off briefly when you need to troubleshoot.

## Step 1: Create the SharePoint lists

Create three lists on the restricted site. Use these internal names exactly (create each column with this name first, then rename the display name if you want). The flow expressions depend on them.

### List A: EDD Config (one row)

This row holds every setting you might change later, so behavior changes never need a flow edit.

| Column | Type | Value to enter on row 1 |
| --- | --- | --- |
| Title | Single line of text | `Owner` |
| LastRunUtc | Single line of text | First run's start point, ISO UTC with Z. Example: `2026-11-16T12:00:00Z` |
| OwnerName | Single line of text | The requester's full name (yours during the build) |
| OwnerEmail | Single line of text | The requester's email (yours during the build) |
| OwnerAliases | Multiple lines (plain text) | Nicknames and initials the requester goes by, comma separated |
| OwnerGroups | Multiple lines (plain text) | Distribution lists and M365 groups the requester is in, comma separated |
| CountGroupRequests | Yes/No | Yes |
| ConfidenceThreshold | Number (2 decimals) | 0.70 |
| ReminderSmallMinutes | Number (0 decimals) | 1440 |
| ReminderBigMinutes | Number (0 decimals) | 4320 |
| DefaultEventTime | Single line of text | `09:00` (24-hour HH:mm) |
| EventCategory | Single line of text | `Auto - Due` (plain hyphen) |
| CalendarId | Multiple lines (plain text) | Test calendar ID (Step 3). Blank = main calendar |
| AlertEmail | Single line of text | Not read by the flow. 8.5 types your address directly so the alert still sends if Get Config fails. Keep it as a record or skip the column |

Note the row's ID (it should be 1). The flow reads and writes this single item.

### List B: EDD Action Items (the flow's memory)

The flow writes one row per item it creates, updates or logs as Maybe. Rows are never deleted by the flow. That is what stops a deleted event from coming back.

| Column | Type | Notes |
| --- | --- | --- |
| Title | Single line of text | Task title from the AI |
| DueDate | Single line of text | `yyyy-MM-dd`. Text on purpose, so it compares and sorts as a string |
| DueTime | Single line of text | `HH:mm` or blank |
| Size | Choice: Small, Big |  |
| Status | Choice: Active, Maybe, EventMissing | EventMissing = the requester deleted the event |
| LastAction | Choice: Created, Updated, Maybe |  |
| ConversationId | Single line of text | **Index this column** (List settings → Indexed columns) |
| DedupeKey | Single line of text | **Index this column** |
| EventId | Multiple lines (plain text) | Graph event ID (about 150 characters) |
| SourceLink | Multiple lines (plain text) | Outlook web link to the latest message in the thread |
| Confidence | Number (2 decimals) |  |
| OwnerReason | Multiple lines (plain text) | Why the AI decided it's the requester's |
| Evidence | Multiple lines (plain text) | Quote of 200 characters or fewer |

Add a view named **Upcoming**, filtered Status = Active, sorted DueDate ascending. It doubles as the requester's to-do list and your testing dashboard.

### List C: EDD Sender Rules (empty at launch)

| Column | Type | Notes |
| --- | --- | --- |
| Title | Single line of text | A full address (`jane@example.com`) or a bare domain (`example.com`), lowercase |
| Rule | Choice: Always, Never | Always overrides every noise filter. Never drops the sender's mail before the AI sees it |
| Notes | Single line of text | Why the rule exists |

## Step 2: Build the AI prompt

The prompt does all of the AI judgment: whose item it is, what the date is, and whether it's already tracked. It returns strict JSON that the flow can parse. The instructions and output format are also in [prompt.md](prompt.md) on their own, for reuse.

**Create it:**

1. In your solution: **New → AI prompt** (or build it in Power Automate → AI hub → Prompts, then **Add existing** to the solution).
2. Name: `EDD Extract Action Items`.
3. Add six **text inputs** (+ Add content → Text input), named exactly: `OwnerProfile`, `AlwaysSenders`, `Today`, `ThreadText`, `ThreadItems`, `OtherOpenItems`. Give each a short sample value so you can test in the editor.
4. Paste the instructions below. Where you see `[InputName]`, delete it and insert that input from the + menu.
5. **Output:** JSON. Paste the example under "Output example" as the format.
6. **Model:** start with the default standard model. Set temperature to 0 if the setting is offered.
7. Test with a real thread pasted into ThreadText. Save.

**Instructions (paste as-is):**

```
You review one email thread for one person, the OWNER, and find work the OWNER must deliver by a due date. Your output creates calendar events, so never invent anything.

OWNER PROFILE:
[OwnerProfile]

ALWAYS SENDERS (requests from these addresses or domains count as the OWNER's even when sent to a group): [AlwaysSenders]

TODAY (Eastern time): [Today]

ITEMS ALREADY TRACKED FOR THIS THREAD:
[ThreadItems]

OTHER OPEN ITEMS TRACKED FROM OTHER THREADS:
[OtherOpenItems]

THREAD (oldest first, each message's body shows only its new text):
[ThreadText]

RULES
1. Ownership. An item is the OWNER's when:
   a) someone asks the OWNER to do something, by name or alias, or in an email sent directly to the OWNER;
   b) the OWNER commits to something in a message the OWNER sent ("I'll send...", "will have it by...");
   c) a request goes to one of the OWNER's groups or to "all/everyone", and the profile says group requests count;
   d) a sender in ALWAYS SENDERS asks the recipients for an action.
   NOT the OWNER's: work clearly assigned to someone else, FYIs, newsletters, marketing, and automated notices without an action the OWNER must take.
2. Dates. Resolve relative dates against the SENT time of the message that contains them, not TODAY.
   - "by Friday" = the first Friday on or after the sent date. "next Friday" = the Friday of the following week.
   - "EOD" or "end of day" = 17:00 that day. "end of week" = Friday. "end of month" = last business day of that month.
   - "next week" with no day = Friday of that week, confidence 0.6 or lower.
   - No date, "ASAP" or "soon" = dueDate "" (empty).
   - Never guess a date that is not stated or clearly implied.
   - If the resolved date is before TODAY, leave the item out.
3. Already tracked. Compare against both tracked lists. Wording can differ; match on the same deliverable.
   - Tracked and nothing changed: leave it out entirely.
   - Tracked but a later message changed the due date, time or the deliverable: return action "update" with existingItemId set to that item's ID number.
   - Not tracked: return action "create" with existingItemId null.
   - If the thread shows an item is done or cancelled, leave it out.
4. title: starts with a verb, 80 characters or fewer, names the deliverable and who it's for. Example: "Send Q4 budget draft to Finance".
5. dueTime: 24-hour "HH:mm" only when a time is stated or implied (EOD = "17:00"); otherwise "".
6. size: "big" for substantial work (a report, presentation, board or audit material, a project milestone, anything that likely needs over 2 hours or several people); otherwise "small".
7. confidence: 0 to 1, for "this is the OWNER's item AND the date is right".
8. ownerReason: 120 characters or fewer, why it's the OWNER's.
9. evidence: 200 characters or fewer, quoting the sentence that sets the task or date.
10. Privacy: never copy account numbers, SSNs, card numbers or member personal details into title or evidence. Replace them with [masked].
11. Return ONLY JSON in the output format. If nothing qualifies, return {"items": []}.
```

**Output example (paste as the JSON format):**

```json
{"items":[{"action":"create","existingItemId":null,"title":"Send Q4 budget draft to Finance","dueDate":"2026-11-20","dueTime":"17:00","size":"big","confidence":0.86,"ownerReason":"Direct request to the owner in the latest message","evidence":"Can you get me the Q4 budget draft by Friday at 5?"}]}
```

## Step 3: One-time Outlook setup

Do this in whichever mailbox the flow is pointed at: yours during the build, the requester's before their test week.

1. **Test calendar.** Outlook on the web → Calendar → **Add calendar → Create blank calendar** → name it `Due Dates (Test)`.
2. **Get its ID.** Make a throwaway *instant* flow with one action: Office 365 Outlook → **Get calendars (V2)**. Run it, open the output, find the object whose `name` is `Due Dates (Test)`, and copy its `id` into **CalendarId** on the Config row. Delete the throwaway flow.
3. **Category color (optional).** In Outlook, right-click any event → **Categorize → New category** → `Auto - Due`, and pick a color. If you skip this, the events still get the category, just without a color.

## Step 4: Flow shell: trigger, variables, settings

In the solution: **New → Automation → Cloud flow → Scheduled**. Name it `EDD Email Due Dates (Requester)`.

**4.1 Trigger: Recurrence**

- Interval: `1`, Frequency: `Week`
- Time zone: `(UTC-05:00) Eastern Time (US & Canada)`
- On these days: Monday through Friday
- At these hours: `7`, `16`. At these minutes: `5`

Weekend mail is picked up Monday at 7:05 AM, because each run reads everything since the last saved watermark.

**4.2 Initialize variables.** Add seven **Variables → Initialize variable** actions directly under the trigger, outside any scope:

| Action name | Name | Type | Value |
| --- | --- | --- | --- |
| Init RunStart | varRunStartUtc | String | fx `utcNow('yyyy-MM-ddTHH:mm:ssZ')` |
| Init Today | varToday | String | fx `convertFromUtc(utcNow(), 'Eastern Standard Time', 'yyyy-MM-dd')` |
| Init Created | varCreated | String | leave blank |
| Init Updated | varUpdated | String | leave blank |
| Init Maybe | varMaybe | String | leave blank |
| Init Reminder | varReminderMinutes | Integer | `0` |
| Init Skipped | varSkipped | String | leave blank |

varRunStartUtc is captured before any mail is read. It becomes the next watermark, so mail that arrives while the flow is running gets picked up next time. The format string drops the fractional seconds, so the saved watermark has the same `2026-11-16T11:00:00Z` shape as the Config example and the mail filters.

**4.3 Control → Scope, renamed "Try".** Every action in Steps 4.4 through 8.4 goes **inside** Try.

**4.4 SharePoint → Get item, renamed "Get Config"**

- Site Address: the restricted site (choose from the dropdown)
- List Name: `EDD Config`
- Id: `1`

**4.5 SharePoint → Get items, renamed "Get Sender Rules"**

- Site Address: the restricted site
- List Name: `EDD Sender Rules`
- Top Count (Advanced parameters): `500`

**4.6 Data Operation → Filter array, renamed "Filter Never Rules"**

- From: fx `body('Get_Sender_Rules')?['value']`
- Click **Edit in advanced mode** and paste: `@equals(item()?['Rule']?['Value'], 'Never')`

**4.7 Data Operation → Select, renamed "Select Never Senders"**

- From: fx `body('Filter_Never_Rules')`
- Click the **Switch Map to text mode** toggle, then Map: fx `toLower(trim(item()?['Title']))`
- The output is a plain array of strings, like `["example.com","news@contoso.com"]`.

**4.8 The same pair for Always senders.** Two actions:

- **Data Operation → Filter array, renamed "Filter Always Rules"**
  - From: fx `body('Get_Sender_Rules')?['value']`
  - Click **Edit in advanced mode** and paste: `@equals(item()?['Rule']?['Value'], 'Always')`
- **Data Operation → Select, renamed "Select Always Senders"**
  - From: fx `body('Filter_Always_Rules')`
  - Click the **Switch Map to text mode** toggle, then Map: fx `toLower(trim(item()?['Title']))`

**4.9 Data Operation → Compose, renamed "Always Senders Text"**

- Inputs: fx `if(empty(body('Select_Always_Senders')), 'None', join(body('Select_Always_Senders'), ', '))`

## Step 5: Get new mail, filter it, group by thread

Still inside **Try**, directly under "Always Senders Text".

**5.1 Office 365 Outlook → Send an HTTP request, renamed "Get New Inbox Mail"**

- URI: fx

```
concat('https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages?$filter=', encodeUriComponent(concat('receivedDateTime ge ', formatDateTime(body('Get_Config')?['LastRunUtc'], 'yyyy-MM-ddTHH:mm:ssZ'))), '&$select=id,conversationId,subject,from,receivedDateTime&$top=500')
```

- Method: `GET`
- Body, Content-Type, headers: leave blank

formatDateTime() turns whatever is in LastRunUtc into the ISO form Graph's filter needs, so a watermark saved as `11/13/2026 20:51:43` (or a Date and Time column) still works.

The response is `{ "value": [ ...messages ] }`. Calendar invites come back with `@odata.type` = `#microsoft.graph.eventMessage...`. That's how they get filtered out in 5.4.

**5.2 Office 365 Outlook → Send an HTTP request, renamed "Get New Sent Mail"**

The same call against the Sent Items folder, filtered on sent time instead of received time.

- URI: fx

```
concat('https://graph.microsoft.com/v1.0/me/mailFolders/sentitems/messages?$filter=', encodeUriComponent(concat('sentDateTime ge ', formatDateTime(body('Get_Config')?['LastRunUtc'], 'yyyy-MM-ddTHH:mm:ssZ'))), '&$select=id,conversationId,subject,from,receivedDateTime&$top=500')
```

- Method: `GET`
- Body, Content-Type, headers: leave blank

**5.3 Data Operation → Compose, renamed "All New Mail"**

- Inputs: fx `union(body('Get_New_Inbox_Mail')?['value'], body('Get_New_Sent_Mail')?['value'])`

**5.4 Data Operation → Filter array, renamed "Filter Out Noise"**

- From: fx `outputs('All_New_Mail')`
- **Edit in advanced mode**, paste this as a single line. Always-senders pass no matter what. Everything else must not be an invite, an auto-reply, a no-reply sender, or a Never sender (full address or domain).

```
@or(contains(body('Select_Always_Senders'), toLower(string(item()?['from']?['emailAddress']?['address']))), contains(body('Select_Always_Senders'), toLower(last(split(string(item()?['from']?['emailAddress']?['address']), '@')))), and(not(startsWith(string(item()?['@odata.type']), '#microsoft.graph.eventMessage')), not(startsWith(toLower(string(item()?['subject'])), 'automatic reply')), not(contains(toLower(string(item()?['from']?['emailAddress']?['address'])), 'noreply')), not(contains(toLower(string(item()?['from']?['emailAddress']?['address'])), 'no-reply')), not(contains(body('Select_Never_Senders'), toLower(string(item()?['from']?['emailAddress']?['address'])))), not(contains(body('Select_Never_Senders'), toLower(last(split(string(item()?['from']?['emailAddress']?['address']), '@')))))))
```

**5.5 Data Operation → Select, renamed "Select Conversation Ids"**

- From: fx `body('Filter_Out_Noise')`
- Text mode, Map: fx `item()?['conversationId']`

**5.6 Data Operation → Compose, renamed "Distinct Threads"**

- Inputs: fx `union(body('Select_Conversation_Ids'), body('Select_Conversation_Ids'))`
- union() of an array with itself returns each conversationId once. Ten emails in one thread become one AI call.

**5.7 Data Operation → Compose, renamed "Owner Profile"**

Place it inside **Try**, directly above For Each Thread, not inside the loop. It's the same for every thread, so building it once per run is enough.

Type the labels as plain text. Insert each value as an fx expression on the same line:

```
Name: [fx body('Get_Config')?['OwnerName']]
Email: [fx body('Get_Config')?['OwnerEmail']]
Also known as: [fx body('Get_Config')?['OwnerAliases']]
Groups the owner belongs to: [fx body('Get_Config')?['OwnerGroups']]
Group requests count as the owner's: [fx if(equals(body('Get_Config')?['CountGroupRequests'], true), 'yes', 'no')]
```

## Step 6: Loop each thread and call the prompt

**6.1 Control → Apply to each, renamed "For Each Thread"** (inside Try, under Owner Profile)

- Select an output from previous steps: fx `outputs('Distinct_Threads')`
- Settings: leave **Concurrency control off**. The loop must run one thread at a time, because it appends to shared string variables.

Steps 6.1a through 7 all go **inside** For Each Thread.

**6.1a Control → Scope, renamed "Thread Try"** (the first action inside For Each Thread)

Every action from 6.1b through 7 goes inside Thread Try. Without it, one bad thread (cut-off AI JSON, a date the flow can't parse, a 400 from Graph) fails the whole run. The watermark then never advances, so every later run rereads the same mail and fails on the same thread.

Directly under Thread Try, still inside For Each Thread, add **Variables → Append to string variable, renamed "Note Skipped"**:

- Name: `varSkipped`
- Value: fx `concat('<li>', coalesce(body('Get_Thread_Messages')?['value']?[0]?['subject'], items('For_Each_Thread')), '</li>')`
- Configure run after → Thread Try: check **has failed** and **has timed out**, uncheck **is successful**

A skipped thread isn't retried by itself. It's read again the next time a new message lands in it, and 8.3a tells you which threads were skipped.

**Cross-thread dedupe: 6.1b through 6.1e are the first four actions inside Thread Try, above 6.2.** They re-read open items for every thread. If two threads in the same run mention the same task, the second one sees the row the first one just created and doesn't make a second event. The cost is one extra SharePoint call per thread.

**6.1b SharePoint → Get items, renamed "Get Open Items"** (open items from all threads)

- Site Address: the restricted site
- List Name: `EDD Action Items`
- Filter Query: `Status eq 'Active'`
- Top Count: `500`

**6.1c Data Operation → Filter array, renamed "Filter Upcoming Items"**

- From: fx `body('Get_Open_Items')?['value']`
- Advanced mode: `@greaterOrEquals(string(item()?['DueDate']), variables('varToday'))`
- This works because DueDate is stored as `yyyy-MM-dd` text, which compares correctly as a string.

**6.1d Data Operation → Select, renamed "Select Other Open Items"**

- From: fx `body('Filter_Upcoming_Items')`
- Text mode, Map: fx `concat('ID ', item()?['ID'], ': ', item()?['Title'], ' | due ', item()?['DueDate'])`

**6.1e Data Operation → Compose, renamed "Other Open Items Text"**

- Inputs: fx `if(empty(body('Select_Other_Open_Items')), 'None', join(body('Select_Other_Open_Items'), decodeUriComponent('%0A')))`

**6.2 Office 365 Outlook → Send an HTTP request, renamed "Get Thread Messages"**

This pulls the thread's recent history, not only the new messages. A reply like "Will do" only makes sense next to the request it answers.

- URI: fx

```
concat('https://graph.microsoft.com/v1.0/me/messages?$filter=', encodeUriComponent(concat('conversationId eq ''', items('For_Each_Thread'), '''')), '&$select=id,conversationId,subject,from,toRecipients,ccRecipients,receivedDateTime,uniqueBody,webLink&$top=50')
```

- Method: `GET`
- Advanced parameters → **CustomHeader1**: `Prefer: outlook.body-content-type="text"` (returns plain text instead of HTML, which is far fewer tokens)
- `uniqueBody` is only the new text in each message, without the quoted history below it.

**6.3 Data Operation → Compose, renamed "Latest Thread Messages"** (the last 8 messages, oldest first)

- Inputs: fx `reverse(take(reverse(sort(body('Get_Thread_Messages')?['value'], 'receivedDateTime')), 8))`

**6.4 Data Operation → Select, renamed "Select Thread Lines"**

- From: fx `outputs('Latest_Thread_Messages')`
- Text mode, Map: fx

```
concat('--- Sent ', convertFromUtc(item()?['receivedDateTime'], 'Eastern Standard Time', 'dddd, MMMM d, yyyy h:mm tt'), ' | From: ', item()?['from']?['emailAddress']?['name'], ' <', item()?['from']?['emailAddress']?['address'], '> | To: ', string(item()?['toRecipients']), ' | Cc: ', string(item()?['ccRecipients']), ' | Subject: ', item()?['subject'], decodeUriComponent('%0A'), take(string(item()?['uniqueBody']?['content']), 3000))
```

The weekday in the sent stamp ("Wednesday, November 18...") is what lets the model resolve "by Friday" correctly.

**6.5 Data Operation → Compose, renamed "Thread Text"**

- Inputs: fx

```
if(greater(length(join(body('Select_Thread_Lines'), decodeUriComponent('%0A%0A'))), 20000), substring(join(body('Select_Thread_Lines'), decodeUriComponent('%0A%0A')), sub(length(join(body('Select_Thread_Lines'), decodeUriComponent('%0A%0A'))), 20000), 20000), join(body('Select_Thread_Lines'), decodeUriComponent('%0A%0A')))
```

- This keeps the last 20,000 characters of the thread to control credit use. It trims from the oldest end, so the newest messages, which usually hold the date change or the commitment, always reach the AI.

**6.6 Data Operation → Compose, renamed "Source Link"**

- Inputs: fx `last(outputs('Latest_Thread_Messages'))?['webLink']`

**6.7 SharePoint → Get items, renamed "Get Thread Items"**

- Site Address: the restricted site
- List Name: `EDD Action Items`
- Filter Query: type `ConversationId eq '`, insert fx `items('For_Each_Thread')`, then type the closing `'`
- Top Count: `50`
- No Status filter here on purpose. Maybe and EventMissing rows must also count as "already tracked".

**6.8 Data Operation → Select, renamed "Select Thread Items"**

- From: fx `body('Get_Thread_Items')?['value']`
- Text mode, Map: fx `concat('ID ', item()?['ID'], ': ', item()?['Title'], ' | due ', coalesce(item()?['DueDate'], 'none'), ' | status ', item()?['Status']?['Value'])`

**6.9 Data Operation → Compose, renamed "Thread Items Text"**

- Inputs: fx `if(empty(body('Select_Thread_Items')), 'None', join(body('Select_Thread_Items'), decodeUriComponent('%0A')))`

**6.10 AI Builder → Run a prompt, renamed "Extract Action Items"**

- Prompt: `EDD Extract Action Items`
- OwnerProfile: fx `outputs('Owner_Profile')`
- AlwaysSenders: fx `outputs('Always_Senders_Text')`
- Today: fx `concat(convertFromUtc(utcNow(), 'Eastern Standard Time', 'dddd, MMMM d, yyyy'), ' (', variables('varToday'), ')')`
- ThreadText: fx `outputs('Thread_Text')`
- ThreadItems: fx `outputs('Thread_Items_Text')`
- OtherOpenItems: fx `outputs('Other_Open_Items_Text')`

**6.11 Data Operation → Compose, renamed "Clean AI Output"** (strips the markdown fences models sometimes add)

- Inputs: fx

````
trim(replace(replace(string(outputs('Extract_Action_Items')?['body/responsev2/predictionOutput/text']), '```json', ''), '```', ''))
````

- If the prompt action shows a **Text** dynamic-content token, it is this same value. Check your first run's raw output to confirm the path.

**6.12 Data Operation → Parse JSON, renamed "Parse AI Items"**

- Content: fx `outputs('Clean_AI_Output')`
- Schema (paste):

```json
{"type":"object","properties":{"items":{"type":"array","items":{"type":"object","properties":{"action":{"type":"string"},"existingItemId":{"type":["integer","null"]},"title":{"type":"string"},"dueDate":{"type":["string","null"]},"dueTime":{"type":["string","null"]},"size":{"type":["string","null"]},"confidence":{"type":"number"},"ownerReason":{"type":["string","null"]},"evidence":{"type":["string","null"]}},"required":["action","title"]}}},"required":["items"]}
```

## Step 7: Create, update or skip each item

Every item the AI returns goes through three duplicate checks before anything touches the calendar:

1. The prompt itself left out anything already tracked.
2. **create** only runs when no row has the same DedupeKey (due date + first 30 characters of the title).
3. **update** only runs against a row ID that really exists for this thread or among open items, and never against an event the requester deleted.

**Branch map for this step** (build in this order):

- For Each Item
  - Prep: 7.2 to 7.10
  - Switch Action
    - Case **create** → Find Duplicate → Is New?
      - Yes → Confident and Dated?
        - Yes → Create Calendar Event → Log Created → append to varCreated
        - No → Log Maybe → append to varMaybe
      - No → nothing (duplicate)
    - Case **update** → Find Existing Item → Found Existing?
      - Yes → Has Event?
        - Yes → Try Patch → Patch Worked? then Event Gone? (a separate condition below Patch Worked)
          - Patch Worked yes → Log Updated → append to varUpdated
          - Patch Worked no → nothing; Event Gone yes (404) → Mark Event Missing
        - No (it was a Maybe) → Now Confident?
          - Yes → Create Event From Maybe → Promote Maybe → append to varCreated
      - No → nothing
    - Default → nothing

### 7.1 Control → Apply to each, renamed "For Each Item"

- Inside Thread Try, under Parse AI Items
- Select an output from previous steps: fx `body('Parse_AI_Items')?['items']`
- Concurrency control: **off**

### Prep actions (inside For Each Item)

**7.2 Variables → Set variable, renamed "Set Reminder"**

- Name: `varReminderMinutes`
- Value: fx

```
if(equals(toLower(coalesce(items('For_Each_Item')?['size'], 'small')), 'big'), int(body('Get_Config')?['ReminderBigMinutes']), int(body('Get_Config')?['ReminderSmallMinutes']))
```

**7.3 Data Operation → Compose, renamed "Item Title Safe"**

This strips double quotes, backslashes, line breaks, carriage returns and tabs so the event JSON can never break.

- Inputs: fx

```
take(replace(replace(replace(replace(replace(trim(items('For_Each_Item')?['title']), '"', ''''), '\', '/'), decodeUriComponent('%0A'), ' '), decodeUriComponent('%0D'), ' '), decodeUriComponent('%09'), ' '), 120)
```

**7.4 Data Operation → Compose, renamed "Item Evidence Safe"**

- Inputs: fx

```
take(replace(replace(replace(replace(replace(coalesce(items('For_Each_Item')?['evidence'], ''), '"', ''''), '\', '/'), decodeUriComponent('%0A'), ' '), decodeUriComponent('%0D'), ' '), decodeUriComponent('%09'), ' '), 200)
```

**7.5 Data Operation → Compose, renamed "Item Due Date"**

- Inputs: fx `coalesce(items('For_Each_Item')?['dueDate'], '')`

**7.6 Data Operation → Compose, renamed "Item Due Time"**

- Inputs: fx `coalesce(items('For_Each_Item')?['dueTime'], '')`

**7.7 Data Operation → Compose, renamed "Dedupe Key"** (apostrophes are removed so the key is safe inside a SharePoint filter)

- Inputs: fx

```
toLower(concat(outputs('Item_Due_Date'), '|', take(replace(replace(replace(replace(outputs('Item_Title_Safe'), ' ', ''), '''', ''), '.', ''), ',', ''), 30)))
```

**7.8 Data Operation → Compose, renamed "Anchor DateTime"**

This is always a valid date-time, even when the date is missing (it falls back to 2000-01-01), so the math in 7.9 never errors.

- Inputs: fx

```
concat(if(empty(outputs('Item_Due_Date')), '2000-01-01', outputs('Item_Due_Date')), 'T', if(empty(outputs('Item_Due_Time')), body('Get_Config')?['DefaultEventTime'], outputs('Item_Due_Time')), ':00')
```

**7.9 Two Composes for the event window.** If there's no stated time, the event is 9:00–9:15 AM on the due date. If there is a time, the event is the 30 minutes ending at that time.

- **Data Operation → Compose, renamed "Event Start"**
  - Inputs: fx `if(empty(outputs('Item_Due_Time')), outputs('Anchor_DateTime'), formatDateTime(addMinutes(outputs('Anchor_DateTime'), -30), 'yyyy-MM-ddTHH:mm:ss'))`
- **Data Operation → Compose, renamed "Event End"**
  - Inputs: fx `if(empty(outputs('Item_Due_Time')), formatDateTime(addMinutes(outputs('Anchor_DateTime'), 15), 'yyyy-MM-ddTHH:mm:ss'), outputs('Anchor_DateTime'))`

**7.10 Two more Composes**

- **Data Operation → Compose, renamed "Is Confident"**
  - Inputs: fx `and(not(empty(outputs('Item_Due_Date'))), greaterOrEquals(float(coalesce(items('For_Each_Item')?['confidence'], 0)), float(body('Get_Config')?['ConfidenceThreshold'])))`
- **Data Operation → Compose, renamed "Event Payload"**
  - Inputs: paste the JSON below. Each `@{...}` is an fx expression token: delete the placeholder text and insert the expression. Keep the quotes around string tokens. The reminder token goes in with **no quotes**, so Graph receives a number.

```json
{
  "subject": "Due: @{outputs('Item_Title_Safe')}",
  "body": {
    "contentType": "HTML",
    "content": "<p>Added automatically from your email.</p><p><b>Why:</b> @{outputs('Item_Evidence_Safe')}</p><p><a href='@{outputs('Source_Link')}'>Open the email thread</a></p>"
  },
  "start": { "dateTime": "@{outputs('Event_Start')}", "timeZone": "Eastern Standard Time" },
  "end": { "dateTime": "@{outputs('Event_End')}", "timeZone": "Eastern Standard Time" },
  "showAs": "free",
  "isReminderOn": true,
  "reminderMinutesBeforeStart": @{variables('varReminderMinutes')},
  "categories": [ "@{body('Get_Config')?['EventCategory']}" ]
}
```

### 7.11 Control → Switch, renamed "Switch Action"

- On: fx `toLower(items('For_Each_Item')?['action'])`
- Case 1 equals: `create`
- Case 2 equals: `update`
- Default: leave empty

### Case create

**7.12 SharePoint → Get items, renamed "Find Duplicate"**

- Site Address: the restricted site
- List Name: `EDD Action Items`
- Filter Query: type `DedupeKey eq '`, insert fx `outputs('Dedupe_Key')`, then type the closing `'`
- Top Count: `1`

**7.13 Control → Condition, renamed "Is New"**

- fx `length(body('Find_Duplicate')?['value'])` **is equal to** `0`
- Leave the False branch empty.

**7.14 In True: Control → Condition, renamed "Confident and Dated"**

- fx `outputs('Is_Confident')` **is equal to** fx `true`

**7.15 In True: Office 365 Outlook → Send an HTTP request, renamed "Create Calendar Event"**

- URI: fx `if(empty(trim(coalesce(body('Get_Config')?['CalendarId'], ''))), 'https://graph.microsoft.com/v1.0/me/events', concat('https://graph.microsoft.com/v1.0/me/calendars/', trim(body('Get_Config')?['CalendarId']), '/events'))`
- Method: `POST`
- Body: fx `outputs('Event_Payload')`
- Content-Type: `application/json`

**7.16 SharePoint → Create item, renamed "Log Created"**

- Site Address: the restricted site
- List Name: `EDD Action Items`

| Field | Value |
| --- | --- |
| Title | fx `outputs('Item_Title_Safe')` |
| DueDate | fx `outputs('Item_Due_Date')` |
| DueTime | fx `outputs('Item_Due_Time')` |
| Size Value | Enter custom value → fx `if(equals(toLower(coalesce(items('For_Each_Item')?['size'], 'small')), 'big'), 'Big', 'Small')` |
| Status Value | `Active` |
| LastAction Value | `Created` |
| ConversationId | fx `items('For_Each_Thread')` |
| DedupeKey | fx `outputs('Dedupe_Key')` |
| EventId | fx `body('Create_Calendar_Event')?['id']` |
| SourceLink | fx `outputs('Source_Link')` |
| Confidence | fx `items('For_Each_Item')?['confidence']` |
| OwnerReason | fx `coalesce(items('For_Each_Item')?['ownerReason'], '')` |
| Evidence | fx `outputs('Item_Evidence_Safe')` |

**7.17 Variables → Append to string variable, renamed "Note Created"**

- Name: `varCreated`
- Value: fx `concat('<li>', outputs('Item_Title_Safe'), ' (due ', formatDateTime(outputs('Anchor_DateTime'), 'ddd, MMM d'), ')</li>')`

**7.18 In the False branch of Confident and Dated: SharePoint → Create item, renamed "Log Maybe"**

No calendar event is created.

- Site Address: the restricted site
- List Name: `EDD Action Items`

| Field | Value |
| --- | --- |
| Title | fx `outputs('Item_Title_Safe')` |
| DueDate | fx `outputs('Item_Due_Date')` (may be blank) |
| DueTime | fx `outputs('Item_Due_Time')` |
| Size Value | Enter custom value → fx `if(equals(toLower(coalesce(items('For_Each_Item')?['size'], 'small')), 'big'), 'Big', 'Small')` |
| Status Value | `Maybe` |
| LastAction Value | `Maybe` |
| ConversationId | fx `items('For_Each_Thread')` |
| DedupeKey | fx `outputs('Dedupe_Key')` |
| EventId | leave blank |
| SourceLink | fx `outputs('Source_Link')` |
| Confidence | fx `items('For_Each_Item')?['confidence']` |
| OwnerReason | fx `coalesce(items('For_Each_Item')?['ownerReason'], '')` |
| Evidence | fx `outputs('Item_Evidence_Safe')` |

**7.19 Variables → Append to string variable, renamed "Note Maybe"** (still in the False branch, under Log Maybe)

- Name: `varMaybe`
- Value: fx `concat('<li>', outputs('Item_Title_Safe'), if(empty(outputs('Item_Due_Date')), ' (no clear date)', concat(' (possibly ', outputs('Item_Due_Date'), ')')), '</li>')`

### Case update

**7.20 Data Operation → Filter array, renamed "Find Existing Item"**

Rows marked EventMissing are excluded, so a deleted event is never touched again.

- From: fx `union(body('Get_Thread_Items')?['value'], body('Filter_Upcoming_Items'))`
- Advanced mode: `@and(equals(item()?['ID'], coalesce(items('For_Each_Item')?['existingItemId'], -1)), not(equals(item()?['Status']?['Value'], 'EventMissing')))`

**7.21 Control → Condition, renamed "Found Existing"**

- fx `length(body('Find_Existing_Item'))` **is greater than** `0`
- Leave False empty.

**7.22 In True: Data Operation → Compose, renamed "Existing Item"**

- Inputs: fx `first(body('Find_Existing_Item'))`

**7.23 Control → Condition, renamed "Has Event"** (under Existing Item)

- fx `and(not(empty(outputs('Existing_Item')?['EventId'])), outputs('Is_Confident'))` **is equal to** fx `true`

Is Confident is part of this check so an update without a date, or with a low-confidence one, never moves a live event. Without it, an update whose date came back blank would PATCH the event to the 2000-01-01 fallback from 7.8. A low-confidence update on a row that already has an event drops to Now Confident in the False branch, which is also false, so nothing changes.

**7.24 In True: Control → Scope, renamed "Try Patch"**, containing one action:

- **Office 365 Outlook → Send an HTTP request, renamed "Update Calendar Event"**
  - URI: fx `concat('https://graph.microsoft.com/v1.0/me/events/', trim(outputs('Existing_Item')?['EventId']))`
  - Method: `PATCH`
  - Body: fx `outputs('Event_Payload')`
  - Content-Type: `application/json`
- PATCH changes only the fields sent, and the event ID stays the same, so nothing needs re-linking. A 404 here means the requester deleted the event.

**7.25 Control → Condition, renamed "Patch Worked"** (directly under Try Patch, still in Has Event → True)

- **Configure run after** → check both **is successful** and **has failed** for Try Patch
- Condition: fx `first(result('Try_Patch'))?['status']` **is equal to** `Succeeded`
- **True, first action: SharePoint → Update item, renamed "Log Updated"**
  - Site Address: the restricted site
  - List Name: `EDD Action Items`
  - Id: fx `outputs('Existing_Item')?['ID']`
  - Title: fx `outputs('Item_Title_Safe')`
  - DueDate: fx `outputs('Item_Due_Date')`
  - DueTime: fx `outputs('Item_Due_Time')`
  - Size Value: Enter custom value → fx `if(equals(toLower(coalesce(items('For_Each_Item')?['size'], 'small')), 'big'), 'Big', 'Small')`
  - Status Value: `Active`
  - LastAction Value: `Updated`
  - DedupeKey: fx `outputs('Dedupe_Key')`
  - Confidence: fx `items('For_Each_Item')?['confidence']`
  - Evidence: fx `outputs('Item_Evidence_Safe')`
  - Leave every other field blank. Blank fields in Update item keep their current values.
- **True, second action: Variables → Append to string variable, renamed "Note Updated"**
  - Name: `varUpdated`
  - Value: fx `concat('<li>', outputs('Item_Title_Safe'), ' (now due ', formatDateTime(outputs('Anchor_DateTime'), 'ddd, MMM d'), ')</li>')`
- **False:** leave empty. Event Gone goes below Patch Worked (7.25a), not in this branch.

**7.25a Control → Condition, renamed "Event Gone"** (directly **below** the whole Patch Worked block, still inside Has Event → True)

- Condition: fx `outputs('Update_Calendar_Event')?['statusCode']` **is equal to** `404`
- Run after: leave the default (is successful). Patch Worked itself always succeeds, whichever branch it took.
- False: leave empty.
- **True: SharePoint → Update item, renamed "Mark Event Missing"**
  - Site Address: the restricted site
  - List Name: `EDD Action Items`
  - Id: fx `outputs('Existing_Item')?['ID']`
  - Title: fx `outputs('Existing_Item')?['Title']`
  - Status Value: `EventMissing`

**Why it isn't inside Patch Worked → False:** that puts Mark Event Missing 9 levels deep (Try → For Each Thread → Thread Try → For Each Item → Switch → Found Existing → Has Event → Patch Worked → Event Gone), and Power Automate allows at most 8, so the flow won't save. As a sibling it behaves the same: a successful PATCH returns 200, so Event Gone does nothing.

Has Event → True should read:

```
Try Patch
  └ Update Calendar Event
Patch Worked
  ├ True: Log Updated, Note Updated
  └ False: (empty)
Event Gone
  ├ True: Mark Event Missing
  └ False: (empty)
```

A failed PATCH that's handled this way doesn't fail the run. The run's status comes from the last actions, and those succeed.

Only a 404 means the requester deleted the event. Any other failure (throttling, a Graph outage, a bad payload) leaves the row alone, so the next update from email tries again instead of giving up on a live event for good. The Phase 1 delete test should show 404 on Update Calendar Event.

**7.26 In the False branch of Has Event (the row was a Maybe): Control → Condition, renamed "Now Confident"**

- fx `outputs('Is_Confident')` **is equal to** fx `true`
- Leave False empty. In True:
- **First: Office 365 Outlook → Send an HTTP request, renamed "Create Event From Maybe"**
  - URI: fx `if(empty(trim(coalesce(body('Get_Config')?['CalendarId'], ''))), 'https://graph.microsoft.com/v1.0/me/events', concat('https://graph.microsoft.com/v1.0/me/calendars/', trim(body('Get_Config')?['CalendarId']), '/events'))`
  - Method: `POST`
  - Body: fx `outputs('Event_Payload')`
  - Content-Type: `application/json`
- **Second: SharePoint → Update item, renamed "Promote Maybe"**
  - Site Address: the restricted site
  - List Name: `EDD Action Items`
  - Id: fx `outputs('Existing_Item')?['ID']`
  - Title: fx `outputs('Item_Title_Safe')`
  - DueDate: fx `outputs('Item_Due_Date')`
  - DueTime: fx `outputs('Item_Due_Time')`
  - Size Value: Enter custom value → fx `if(equals(toLower(coalesce(items('For_Each_Item')?['size'], 'small')), 'big'), 'Big', 'Small')`
  - Status Value: `Active`
  - LastAction Value: `Created`
  - DedupeKey: fx `outputs('Dedupe_Key')`
  - EventId: fx `body('Create_Event_From_Maybe')?['id']`
  - Confidence: fx `items('For_Each_Item')?['confidence']`
  - Evidence: fx `outputs('Item_Evidence_Safe')`
- **Third: Variables → Append to string variable, renamed "Note Promoted"**
  - Name: `varCreated`
  - Value: fx `concat('<li>', outputs('Item_Title_Safe'), ' (due ', formatDateTime(outputs('Anchor_DateTime'), 'ddd, MMM d'), ')</li>')`

**Note:** an update overwrites the event's subject, time, body and reminder. If the requester changed one of those by hand, a later update from email will replace their change.

## Step 8: Summary, watermark and error handling

The summary is the trust-builder: the requester sees what was added and why, without approving anything. The watermark only advances when the whole run succeeds.

**8.1 Data Operation → Compose, renamed "Summary Html"** (inside Try, **after** For Each Thread, not inside it)

- Inputs: fx

```
concat(if(empty(variables('varCreated')), '', concat('<b>Added to your calendar</b><ul>', variables('varCreated'), '</ul>')), if(empty(variables('varUpdated')), '', concat('<b>Updated</b><ul>', variables('varUpdated'), '</ul>')), if(empty(variables('varMaybe')), '', concat('<b>Possible items, not added</b><ul>', variables('varMaybe'), '</ul><p>Add any of these yourself if they matter.</p>')))
```

**8.2 Control → Condition, renamed "Anything To Report"**

- fx `empty(outputs('Summary_Html'))` **is equal to** fx `false`
- Leave False empty, so quiet runs send nothing.

**8.3 In True: Microsoft Teams → Post message in a chat or channel, renamed "Post Summary"**

- Post as: `Flow bot`
- Post in: `Chat with Flow bot`
- Recipient: fx `body('Get_Config')?['OwnerEmail']`
- Message: type `Email due-date check: ` and then insert fx `outputs('Summary_Html')`. Optionally add a link to the **Upcoming** view of EDD Action Items as a last line.

**8.3a Control → Condition, renamed "Anything Skipped"** (after Anything To Report, before Save Watermark)

- fx `empty(variables('varSkipped'))` **is equal to** fx `false`
- Leave False empty.
- **In True: Microsoft Teams → Post message in a chat or channel, renamed "Alert Skipped"**
  - Post as: `Flow bot`
  - Post in: `Chat with Flow bot`
  - Recipient: type your email directly
  - Message: type `EDD skipped these threads in the requester's mailbox: `, insert fx `concat('<ul>', variables('varSkipped'), '</ul>')`, type `. Open the run to see which action failed. `, then insert fx `concat('https://make.powerautomate.com/environments/', workflow()?['tags']?['environmentName'], '/flows/', workflow()?['name'], '/runs/', workflow()?['run']?['name'])`

**8.4 SharePoint → Update item, renamed "Save Watermark"** (inside Try, the **last** action, after Anything Skipped)

- Site Address: the restricted site
- List Name: `EDD Config`
- Id: `1`
- Title: `Owner`
- LastRunUtc: fx `variables('varRunStartUtc')`

**8.5 Control → Scope, renamed "Catch"** (below Try, outside it)

- **Configure run after** → Try: check **has failed** and **has timed out**, uncheck is successful
- **Inside Catch, first action: Microsoft Teams → Post message in a chat or channel, renamed "Alert Builder"**
  - Post as: `Flow bot`
  - Post in: `Chat with Flow bot`
  - Recipient: type your email directly (not from Config), so the alert still sends if Get Config is what failed
  - Message: type `EDD due-date flow failed for the requester's mailbox. Run: ` then insert fx `concat('https://make.powerautomate.com/environments/', workflow()?['tags']?['environmentName'], '/flows/', workflow()?['name'], '/runs/', workflow()?['run']?['name'])`
- **Inside Catch, second action: Control → Terminate, renamed "Mark Failed"**
  - Status: `Failed`
  - Code: `EDD_FAILED`
  - Message: `See Teams alert`

On a failed run, the watermark stays put, so the next run rereads the same window. Events already created in the failed run are not duplicated, because their rows and dedupe keys already exist.

**8.6 Save and run once manually.** Then open the run and check, in order: both mail calls returned `value` arrays, Distinct Threads has the count you expect, Clean AI Output is bare JSON, and each created event appears on the test calendar with the `Auto - Due` category.

## Testing and rollout

The rollout has three phases. The requester's acceptance test is Phase 2: a week on a test calendar with zero duplicates and events they'd actually want.

| Phase | Status |
| --- | --- |
| 1. Builder's mailbox, test calendar | Passed, all ten cases below |
| 2. Requester's one-week pilot, test calendar | Not started |
| 3. Go-live on the requester's main calendar | Not started |

### Phase 1: Your mailbox

Set the Config owner fields to yourself, CalendarId to your test calendar, and LastRunUtc to two days ago. Send yourself these cases and run the flow manually after each batch.

**Result: all ten cases passed.** In the first run, three test emails became events on the correct dates and times. Their date phrases were "Monday", "Wednesday next week" and "11/19 at 11am".

- [x] Direct request with a relative date ("Can you send the vendor review by Friday?"). The event should land on the right Friday at 9:00 AM, with a reminder the day before.
- [x] Your own commitment in Sent Items ("I'll have the draft to you Thursday EOD"). The event should run 4:30–5:00 PM Thursday.
- [x] A request to a group you're in, with `CountGroupRequests = Yes`. It should be created.
- [x] An FYI that mentions a date but asks nothing of you. Nothing should be created.
- [x] A big deliverable ("board packet due the 30th"). It should be Size = Big, with a 3-day reminder.
- [x] A follow-up that moves the date ("Can we push that to Monday?"). The same event should move (PATCH), and no second event should appear. *In the test, a "can we push that to Tuesday?" reply moved the existing event, with no duplicate.*
- [x] Run the flow twice with no new mail. Nothing new should be created.
- [x] Delete one created event, then reply in its thread. It should not come back.
- [x] A vague request ("sometime next week"). It should appear only as a Maybe in the summary.
- [x] A meeting invite, an out-of-office auto-reply, and an email from a sender you added as a Never rule. None of them should reach the AI. Check that Filter Out Noise's output leaves all three out.

### Phase 2: The requester's test week

Not started.

- [ ] Confirm the requester has a Power Automate Premium license and the environment has Copilot Credits.
- [ ] Add the requester as co-owner of the flow.
- [ ] Share the **EDD Extract Action Items** prompt with the requester (AI hub → Prompts → the prompt → Share, as User). Prompts are private to whoever creates them, so Run a prompt fails under the requester's ownership until it's shared. They also need at least the Basic User security role in the environment.
- [ ] Check the solution's connection references before you swap anything. There should be one per connector, each created in this solution: Office 365 Outlook, SharePoint, Microsoft Teams, and Microsoft Dataverse (Run a prompt uses it). If an action picked up a reference that belongs to another flow, point that action at this solution's reference first. Swapping a shared reference would move the other flow's connection too, and an action left on the old one would keep running as you.
- [ ] With the requester, have them sign into new Office 365 Outlook, SharePoint, Microsoft Teams and Microsoft Dataverse connections. Point each of the solution's connection references at their connections.
- [ ] Change the flow's primary owner to the requester (flow Details → Edit → Owner, or ask your Power Platform admin).
- [ ] Create `Due Dates (Test)` in the requester's Outlook, and put its ID in CalendarId.
- [ ] Update the Config owner fields, aliases and groups for the requester. Set LastRunUtc to the Monday 6:00 AM Eastern of the test week, in UTC (for example `2026-11-16T11:00:00Z`).
- [ ] Ask the requester whether any Outlook rules move mail out of their Inbox. The flow reads only Inbox and Sent Items, so mail a rule files into a subfolder is never seen.
- [ ] Delete all rows in EDD Action Items left over from Phase 1.
- [ ] Turn the flow on. At the end of the week, walk the Upcoming view and the test calendar with the requester. List the misses and the unwanted events, adjust the prompt and the Sender Rules, and repeat for a few days if needed.

### Phase 3: Go live on the requester's main calendar

Not started.

- [ ] Turn the flow off.
- [ ] Delete all rows in EDD Action Items (their events point at the test calendar).
- [ ] Clear CalendarId so events go to the requester's main calendar.
- [ ] Set LastRunUtc back to the start of the test week. The first live run will rebuild every still-upcoming item on the main calendar. The mail calls read at most 500 messages per run, so if that window holds more, see the last Troubleshooting row before you turn the flow on.
- [ ] Turn the flow on, run it once manually, and confirm. Then the requester can delete the test calendar.

**Rollback:** turn the flow off. In Outlook, filter the calendar by the `Auto - Due` category to find and delete everything the flow created.

## Changing behavior later

Group requests can change later, and so can almost everything else. Most changes are a one-cell edit in SharePoint, with no flow edit and no redeploy.

| Change | Where | How |
| --- | --- | --- |
| Stop counting group requests as the requester's | EDD Config | Set CountGroupRequests to No |
| A sender should always or never count | EDD Sender Rules | Add a row with the address or bare domain, Rule = Always or Never |
| Earlier or later heads-up | EDD Config | ReminderSmallMinutes / ReminderBigMinutes (1440 = 1 day, 2880 = 2 days, 4320 = 3 days) |
| Event time when no time is stated | EDD Config | DefaultEventTime, 24-hour HH:mm |
| Fewer or more "Maybe" items | EDD Config | Raise or lower ConfidenceThreshold (0.70 to start) |
| Test calendar or main calendar | EDD Config | CalendarId: a calendar ID, or blank for the main calendar |
| New alias or group for the requester | EDD Config | OwnerAliases / OwnerGroups |
| What counts as a "big" item | Prompt | Rule 6 in EDD Extract Action Items |
| How vague dates are read | Prompt | Rule 2 |
| Run times | Flow | Recurrence trigger hours and minutes |

**Good next versions once the requester trusts v1:**

- **Close the loop.** Add a `complete` action to the prompt for "done" or "cancelled" replies, and DELETE the event with the same HTTP action.
- **Meeting notes.** Pull Teams transcripts after the requester's meetings. This needs Graph permissions that the Outlook connector's HTTP action doesn't cover, so it's a separate design. Facilitator covers their meetings in the meantime.
- **SharePoint REST MERGE for the logging steps.** Replace the four Create/Update item actions with one Compose holding the field values, plus Send an HTTP request to SharePoint (`X-HTTP-Method: MERGE`). That gives one place to maintain the field mapping.

## Troubleshooting

Most first-run errors come from the watermark format or a misnamed action. Rename actions before you write the expressions that reference them.

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Mail call returns 400 "Invalid filter clause" | LastRunUtc isn't ISO UTC with Z | Use the format `2026-11-16T11:00:00Z`. Keep the encodeUriComponent() wrapper, and confirm both mail URIs wrap LastRunUtc in formatDateTime(). "An identifier was expected at position 20" means the date after ge was blank or unreadable |
| HTTP action says the segment isn't supported | URI doesn't start with the Graph `/me` path | URI must begin `https://graph.microsoft.com/v1.0/me/` |
| "The template function 'sort' is not defined" in 6.3 | Older expression support in the environment | Use fx `reverse(take(body('Get_Thread_Messages')?['value'], 8))`. Graph returns newest first by default |
| Message bodies arrive as HTML | CustomHeader1 is missing or mistyped | Re-enter `Prefer: outlook.body-content-type="text"` exactly. HTML still works, just costs more tokens |
| Clean AI Output is blank | With JSON output, the prompt's result can come back under structuredOutput instead of text | In 6.11, change the path to `body/responsev2/predictionOutput/structuredOutput` and keep the string() wrapper |
| Parse AI Items fails | The model returned prose or cut-off JSON | Check Clean AI Output in run history. Confirm the prompt's output is JSON. Lower the 20,000-character cap in 6.5 |
| Prompt action fails with a capacity or credits error | No Copilot Credits in the environment | Allocate credits in the Power Platform admin center |
| Create Calendar Event returns 400 "Unable to read JSON" | Event Payload is malformed | Look at the Compose output in the run. Usually the reminder token is wrapped in quotes, or a placeholder wasn't replaced |
| Event lands one hour off | timeZone string is wrong | Use exactly `Eastern Standard Time`. It handles daylight saving automatically |
| Event lands on the wrong day | A relative date was read against the wrong message | Check that the message's sent stamp in Thread Text shows the weekday. Tighten prompt rule 2 with the failing phrase as an example |
| Duplicate event | The AI returned create for an item that's already tracked, with different wording | Find both rows in EDD Action Items. Confirm the Get Thread Items filter has its quotes. Add the case to prompt rule 3 as an example |
| No Teams summary | Recipient isn't a Teams user, or the Flow bot app is blocked | Check the recipient email. Check the Teams app permission policy for Power Automate |
| Some mail never processed | More than 500 messages in one window | Raise `$top` or add paging on `@odata.nextLink` |

## Sources

- [Microsoft Learn: AI Builder licensing (premium flow requirement)](https://learn.microsoft.com/en-ie/ai-builder/administer-licensing)
- [Microsoft Learn: End of AI Builder credits](https://learn.microsoft.com/ai-builder/endofaibcredits)
- [Microsoft Learn: Copilot Credits for AI Builder](https://learn.microsoft.com/en-us/ai-builder/message-management)
- [Send an HTTP request segments by connector (dev.to)](https://dev.to/kkazala/invoke-an-http-request-without-a-premium-license-connectors-summary-4pmd)
- [Office 365 Outlook connector reference](https://learn.microsoft.com/connectors/office365)
