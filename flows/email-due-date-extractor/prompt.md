# EDD Extract Action Items: the AI prompt

The one AI Builder prompt the [Email Due Dates flow](README.md) calls, once per email thread. It's kept here on its own so it's easy to reuse. The text matches the prompt in the tested build's solution export.

The prompt makes three judgments and nothing else: whether an item is the owner's, what its due date is, and whether it's already tracked. It returns strict JSON. Everything that touches the calendar is flow logic.

## Settings

| Setting | Value |
|---|---|
| Name | `EDD Extract Action Items` |
| Type | AI Builder prompt (AI hub → Prompts), added to the solution |
| Inputs | Six text inputs, listed below |
| Output | JSON, with the example below pasted as the format |
| Model | GPT-4.1 mini, temperature 0 |

The build started on the default, non-premium model on purpose. Premium models cost several times more credits per call, so move up only if quality falls short.

## Inputs

Create six text inputs with exactly these names. In the instructions, each `[InputName]` is the input inserted from the + menu, not typed text.

| Input | What the flow passes | Built by |
|---|---|---|
| `OwnerProfile` | Name, email, aliases, groups, and whether group requests count | `Owner Profile`, from the Config list |
| `AlwaysSenders` | Comma-separated addresses and domains, or `None` | `Always Senders Text`, from the Sender Rules list |
| `Today` | Weekday and date in Eastern time, with the ISO date in parentheses | An expression on the action |
| `ThreadText` | The last 8 messages, oldest first, each with a sent stamp that includes the weekday | `Thread Text` |
| `ThreadItems` | Rows already tracked for this thread, as `ID n: title \| due date \| status`, or `None` | `Thread Items Text` |
| `OtherOpenItems` | Active, upcoming rows from every thread, as `ID n: title \| due date`, or `None` | `Other Open Items Text` |

Two details in the inputs do a lot of the work:

- **The weekday in each sent stamp** is what lets the model resolve "by Friday" against the message that said it.
- **The tracked rows carry their list IDs.** An `update` comes back with `existingItemId`, and the flow only acts on an ID it can find in the rows it sent.

## Instructions

Paste as-is, then replace each `[InputName]` with the input.

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

## Output format

Set the prompt's output to JSON and paste this example as the format:

```json
{"items":[{"action":"create","existingItemId":null,"title":"Send Q4 budget draft to Finance","dueDate":"2026-11-20","dueTime":"17:00","size":"big","confidence":0.86,"ownerReason":"Direct request to the owner in the latest message","evidence":"Can you get me the Q4 budget draft by Friday at 5?"}]}
```

| Field | Values | How the flow uses it |
|---|---|---|
| `action` | `create` or `update` | The Switch. Anything else does nothing |
| `existingItemId` | A list item ID, or `null` | For `update`, the row to change. It must be one of the rows the flow sent |
| `title` | 80 characters or fewer, starts with a verb | Event subject (`Due: ...`) and part of the dedupe key |
| `dueDate` | `yyyy-MM-dd`, or `""` | The event date. Empty means no event: the item is logged as Maybe |
| `dueTime` | `HH:mm`, or `""` | With a time, the event is the 30 minutes ending then. Without one, it's a 15-minute block at the default time |
| `size` | `big` or `small` | Picks the reminder lead time from Config |
| `confidence` | 0 to 1 | Compared with `ConfidenceThreshold`. Below it, the item is logged as Maybe |
| `ownerReason` | 120 characters or fewer | Stored on the ledger row |
| `evidence` | 200 characters or fewer | Stored on the row and shown in the event body |

## What the flow does with the response

The flow doesn't trust the response's shape:

- **Clean AI Output** strips the markdown code fences a model sometimes wraps around JSON.
- **Parse AI Items** uses a looser schema than the prompt's own. Only `action` and `title` are required, and the other fields may be `null`, so one missing field doesn't fail the thread:

```json
{"type":"object","properties":{"items":{"type":"array","items":{"type":"object","properties":{"action":{"type":"string"},"existingItemId":{"type":["integer","null"]},"title":{"type":"string"},"dueDate":{"type":["string","null"]},"dueTime":{"type":["string","null"]},"size":{"type":["string","null"]},"confidence":{"type":"number"},"ownerReason":{"type":["string","null"]},"evidence":{"type":["string","null"]}},"required":["action","title"]}}},"required":["items"]}
```

- **Title and evidence are sanitized** before they go into the event JSON: quotes, backslashes, line breaks, carriage returns and tabs are replaced.
- **A thread whose response can't be parsed is skipped,** not fatal. The run continues, and the builder gets the list of skipped threads.

## Tuning it

| To change | Edit |
|---|---|
| What counts as the owner's | Rule 1. Group requests and Always senders are also switchable in the lists, with no prompt edit |
| How vague or relative dates are read | Rule 2. Add the failing phrase as an example |
| A duplicate created under different wording | Rule 3. Add the case as an example |
| What counts as a "big" item | Rule 6 |
| How many items become Maybe | Not the prompt. Raise or lower `ConfidenceThreshold` in Config |

## Reusing it elsewhere

- **Rule 10 is written for a financial institution.** Swap the list of things to mask for whatever is sensitive in your data.
- **"Eastern time" appears once,** on the TODAY line. Change it along with the flow's time zone strings.
- **Prompts are private to their creator.** A flow that runs the prompt under someone else's connection fails until the prompt is shared with that person.
