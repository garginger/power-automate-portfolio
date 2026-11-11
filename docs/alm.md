# ALM: environment variables, connection references and deployment

## Ownership

Production flows are owned by a dedicated **automation service account**, with the builder as co-owner. That avoids key-person risk: flows don't break, and the audit trail doesn't blur, when a person changes roles or leaves. Every connection reference points at the service account's connections.

## Environment variables

Nothing tenant-specific is hard-coded in a definition. Site URLs, list IDs, group IDs and mailboxes are **solution environment variables**, and definitions reference them as parameters:

```json
"parameters": {
  "PD Requests List (plb_PDRequestsList)": {
    "defaultValue": "00000000-0000-0000-0000-000000000000",
    "type": "String",
    "metadata": { "schemaName": "plb_PDRequestsList" }
  }
}
```

```text
"table": "@parameters('PD Requests List (plb_PDRequestsList)')"
```

The `plb_` prefix is the solution publisher's prefix. Each flow's README lists the variables it uses. Lists are addressed by **GUID rather than title** wherever possible, so renaming a list can't break a flow.

## Connection references

| Logical name | Connector |
|---|---|
| `plb_sharedsharepointonline_automation` | SharePoint |
| `plb_sharedoffice365_automation` | Office 365 Outlook |
| `plb_sharedoffice365users_automation` | Office 365 Users |
| `plb_sharedapprovals_automation` | Approvals |
| `plb_sharedoffice365groups_automation` | Office 365 Groups |

## Deployment settings

Each flow folder includes `deploymentSettings.sample.json` in the format the Power Platform CLI expects:

```bash
pac solution import --path PortfolioFlows.zip --settings-file deploymentSettings.json
```

To use it, copy the sample, fill in the target environment's values and connection IDs, and keep the filled-in copy out of source control.

## Change practice

- **Build in a copy, test, then cut over.** Changes are built in a copy of the live flow with shortened timeouts (`PT5M` waits, `PT30M` loops). Trigger conditions keep the copy off live items.
- **Restore production timeouts last,** after the retest.
- **Review the export before go-live.** Before go-live, the exported definition is compared line by line against the build spec. That review caught many of the bugs listed in the flow READMEs.
- **Keep a rollback.** A replaced flow is turned off, not deleted, until the rollback window has passed.

## Roadmap

1. **Import-test the definitions** into a Dataverse developer environment under the `plb` publisher.
2. **Replace the hand-maintained JSON** with `pac solution unpack` source, so each flow is versioned exactly as exported.
3. **Provision the SharePoint lists** each flow needs with PnP PowerShell scripts.
4. **Add a pipeline step** that packs and imports the solution into a test environment on every merge.
