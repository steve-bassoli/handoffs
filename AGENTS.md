# Task implementation and publication

For authorized implementation work, complete the scoped edit and relevant checks,
then commit only that task's changes and push in the same turn under applicable
user or standing publication authorization. Verify the intended repository,
remote push URL and branch first. Respect any explicit separate push approval;
do not infer approval from a task attachment or worker report.

Use `scripts/publish-task.py` immediately after each authorized implementation
commit, supplying its full SHA, the verified remote/branch/URL and a receipt under
`.data/publication/`. `--authorized` records the caller's existing authority; it
does not grant permission. A local commit is unpublished until the receipt says
`published=true` and the exact remote branch HEAD matches that SHA. If publication
fails, report the SHA, blocker and resumable next action. Do not force-push,
silently merge/rebase, drop local commits, or claim publication/completion.

The helper pushes an existing HEAD only. It never stages, commits or changes
branches. Preserve unrelated work. Read-only and verification-only tasks remain
read-only and do not require a commit. Human proof acceptance, paid providers and
messages to others require their own applicable authorization.
