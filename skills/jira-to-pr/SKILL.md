---
name: jira-to-pr
description: Implement an explicitly selected JIRA ticket through one source-pinned review PR, with no JIRA key in its GitHub title. Use for an explicit JIRA-key launch, not a bounty preview or ordinary board listing.
---

# JIRA ticket to review PR

An explicit `JIRA <key>` or a message containing only a JIRA key launches this
workflow. A bounty listing, claim or preview alone does not. Follow the target
repository's permissions; this skill does not override a GitHub write ban.

1. Retrieve the issue using an available authenticated JIRA source. Preserve
   its key, summary, verbatim requirements/acceptance criteria and SHA-256 source
   fingerprint. Do not mutate JIRA. Stop if the issue cannot be read.
2. Resolve exactly one source repository and full base commit from authoritative
   issue links, project mapping or verified checkout. Ask if ambiguous; never
   implement inside HANDOFFS or Hackwatson by default.
3. Build compact schema-version-2 quest JSON: `taskId` (kebab case), `issueKey`,
   `issueFingerprint`, `summary`, `requirements` (verbatim strings),
   `sourceRepository`, `baseRevision`, `acceptanceCriteria` (empty if absent),
   and optional `constraints`. No credentials, raw exports or unrelated context.
   Run `scripts/prepare-jira-quest.ps1 -QuestJson <json>`. It makes a disposable
   pinned checkout and packages the sibling iterative-implementation contract.
4. Follow the emitted prompt in one executor only when delegation is permitted
   by the user/runtime. Otherwise execute the same bounded contract in the current
   session. Write its retained plan/status before source changes; implement only
   pinned requirements, run their narrow proof, and return the local commit,
   artifacts, conformance statement and unresolved gaps. Do not force-push.
5. Inspect every changed path against the plan and issue requirements. If branch
   and PR publication are authorized, publish one unique non-default branch
   `codex/<lowercase-issue-key>-<slug>` to the verified target repository.
   The PR body retains the key/fingerprint, base, verbatim AC (or `not provided`),
   labeled derived checks, scoped plan summary, changed paths, exact verification
   and gaps. Keep evidence artifacts until verified remote delivery.
6. From the HANDOFFS checkout, create the PR through
   `.venv/Scripts/python.exe -m app.jira_pr --repository <owner/repo>
   --issue-key <key> --summary <authoritative-summary> --body-file <file>
   --base <branch> --head <branch>`; add `--draft` when verification is incomplete.
   The helper removes the issue key from the title and rejects remaining
   JIRA-shaped keys. Never bypass it with a key-prefixed `gh pr create` command.
   Retain the issue key in branch/body, not the title. Attach the created PR to
   the current chat. If creation fails or its outcome is uncertain, inspect remote
   PRs before retrying; never blindly create a second PR.
7. For a claimed HANDOFFS bounty, explicitly authorized delivery records the PR
   and criterion evidence through the service client/MCP with a retained operation
   ID. Demo verification pays automatically; payment is not human acceptance.
   A review bounty requires explicit user authorization and requester-funded Gold;
   do not mint legacy review/merge/intro rewards, write Git packets, or send email.

Never merge, approve, comment, mutate JIRA, or impersonate human acceptance.
The old Tavern intro/review acceptance and local XP/reward workflows are retired.
Report unavailable access/publication precisely without claiming delivery.
