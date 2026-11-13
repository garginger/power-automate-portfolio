# Sanitization

These flows were built for a regulated financial institution, so nothing in this repo identifies the organization, its people, its tenant or its members.

## What was replaced

| Category | Replaced with |
|---|---|
| Organization name, branches, regions | Contoso Credit Union and generic branch names |
| Tenant, site URLs | `contoso.sharepoint.com/sites/...`, exposed as environment variables |
| List, library, group and user IDs | Environment variables with all-zero placeholder GUIDs |
| Email addresses | `role@contoso.com` placeholders (techops, talentdevelopment and so on) |
| People | Roles: program owner, reviewer, requester, branch manager |
| Program names, vendors, internal jargon | Generic equivalents (for example, "Emerging Leaders Program") |
| Member data | None was ever in scope. Definitions contain no data. |

Hard-coded references were converted to environment variables as part of the rebuild, which is also better ALM practice (see [alm.md](alm.md)).

## How it's enforced

[`scripts/check_sanitization.py`](../scripts/check_sanitization.py) runs locally and in CI.

**Generic rules,** committed to the repo, fail the check on:

- any email address outside `contoso.com` or `example.com`
- any SharePoint or tenant host other than `contoso`
- any GUID other than the all-zero placeholder
- anything shaped like a bearer token, JWT or signed URL

**Private rules** cover the real organization's names, people, sites and vendors. Those can't be committed, because the deny-list would publish the very terms it protects. They live in a local file that `.gitignore` excludes:

```bash
python3 scripts/check_sanitization.py --denylist .sanitize-denylist.txt .
```

In CI, the same list can be supplied as a repository secret named `SANITIZE_DENYLIST`, and the workflow applies it when present. CI also runs **gitleaks** over the full history.

## Working with real exports

Raw solution exports (`*.zip`, `exports/`) are gitignored. The workflow is:

1. Export the solution (Unmanaged) into `exports/` and unpack it there.
2. Copy a workflow JSON into its flow folder and replace identifiers with environment variables.
3. Run `validate_definitions.py` and `check_sanitization.py --denylist ...`. Both must pass before commit.

A real export carries more than the workflow JSON. [Email Due Dates](../flows/email-due-date-extractor/) was the first flow sanitized from one, and these needed attention too:

- **Connection reference display names** can carry the names of other flows.
- **An AI prompt's saved test values** can hold real names and addresses.
- **The solution and customizations files** hold the publisher, its description and component IDs. They aren't published here.
- **Designer metadata IDs** on triggers and actions trip the GUID rule.
