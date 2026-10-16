# HANDOFFS prototype migration evidence

October 16, 2026. This records prototype evidence, not a team-wide cutover.

## Application

FastAPI and SQLite own the bounty lifecycle, Gold ledger, monthly grants, reserved funds and payouts. Plain JavaScript and the PowerShell client share the API. Demo identity and PR verification are replaceable adapters. There is no blockchain or production authentication.

Self-verification covered monthly issuance/restart, funding/retries/insufficient balance, concurrent funding and claims, ownership, progress, delivery/payment/repost, cancellation, immutable evidence and explicit review. Browser verification moved 150 Gold from Steve's funded bounty to Nate's wallet (1000 -> 1150). A live PowerShell round trip paid 200 Gold once after a duplicate posting request.

Final canonical checkout verification: 15 tests passed, exit 0, using a fresh `.data/pytest-GUID` directory after a Windows temp ACL conflict. One upstream Starlette/httpx TestClient deprecation warning remains. The canonical server runs on loopback port 8000, background PID 36212. Browser and client verified the imported board and 1000-Gold wallet. No synthetic verification bounties were copied into the canonical database.

## Historical sources

- Git source: `nate-viniconis/hackwatson` at published commit `3102a142b1fbf21c112d5f8de377cd7421e2eb9e`, refreshed during this run.
- All 30 published packets imported with no Git packet gaps. Original context, updates, events, result/review documents and provenance are preserved. Reimport and immutable-record conflicts are tested.
- A repeat import returned 30 unchanged packets and zero new packets, exit 0.
- A read-only consistent local SQLite snapshot contained five profiles and two capacity rows. Existing reward, PR-reward, intro-reward and spending tables contained zero rows.
- Coverage gap: the snapshot had no `relations` table. Its absence is reported; no relationships were invented. Other teammates' local databases were not available, so this is not proof of all team-local data coverage.
- Historical profiles/awards are retained as import records, not promoted into authenticated accounts or spendable currency. Imported quests are read-only/unfunded history. New funded bounties use the normal API.
- Personal data and database snapshots remain outside source control.
- Consistent backups were created with SQLite backup API at `.data/app-backup-4acca91b0d784297857636284179cbfc.sqlite` and `.data/legacy-backup-42684067ce8b49c5aaed666876963334.sqlite` in the canonical checkout.

## Hackwatson retirement candidate

Prepared locally at `C:\work\modern_watson\hackwatson-cutover` on branch `codex/handoffs-service-cutover`, commit `b42fd657512ce175b123fd81e3fb4cb95de17b32`.

The candidate removes the old HANDOFFS skills, helpers, tests and active packet files, installs one `.agents/skills/handoffs/` client with a Claude discovery alias, and replaces obsolete root guidance. Shared skill ownership policies and unrelated Watson code/plans are preserved. Removed files remain recoverable from the parent Git commit. Candidate checks: clean diff whitespace; valid skill; no retired helper references in active skill/root guidance; client stats read from the live service.

Publishing this candidate to Nate's repository was rejected by automatic approval review: code publication to that destination was not explicitly authorized. The commit is local and unpublished; no default branch or PR was changed. Publishing requires Steve's explicit authorization for `nate-viniconis/hackwatson`.

## Activation prerequisites

- The original Hackwatson checkout remains on its original branch with a modified `start` skill and an unpublished quest commit; it was ahead one and behind seven relative to the refreshed published checkpoint. Preserve and reconcile that work before applying the retirement candidate.
- Select a service URL reachable by the intended teammate sessions. The current demo uses loopback; cross-machine reachability is unverified.
- Pause legacy writes, take final consistent source/database snapshots, reimport new events and reconcile any gaps before switching clients.
- Installed `start` and `init-hackwatson` junctions still point at the original checkout. Change them only as part of activation; no existing monitor or user configuration was modified.
- Keep the source revision and database backup as rollback points. Reconcile new service writes before re-enabling old writes.

HF-16 and final team-cutover acceptance remain blocked on these prerequisites. The application can be used locally without activating the retirement candidate.
