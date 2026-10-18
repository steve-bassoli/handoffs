# Protected agent rules — prototype

## Content and compatibility

`agent-rules.json` is the single source for the extracted rule and mission texts. `texts` holds exact runtime string fragments; `compositions` records their concatenation order. Leading/trailing spaces and the separate SPACE fragment are intentional. This preserves the original string values rather than the Python source spelling. Do not reword anything in this extraction, including debt. Task 802aa3f6 stays on hold; this does not depend on sign-off ledger 3babb128.

`app.rules` reads and validates one snapshot at import. Missing/malformed files or absent matching approval raise RulesError; there is no embedded-text fallback. Existing module attributes remain importable. Restart processes after approved changes; a running process retains its loaded snapshot. PRESSURE_RULES preserves the current level-1 text; PRESSURE_LEVEL in the conduit remains existing telemetry, not a separate editable rule-text template.

## Bootstrap activation (human-reviewed deployment)

1. Compare exported old/new runtime strings in an isolated checkout, preserving all spaces. No application or paid API call is required.
2. Write the final JSON bytes. Compute SHA-256 over those bytes, not parsed/reformatted JSON.
3. Fill the same digest into app/rules.py BOOTSTRAP_SHA256 and the bootstrap entry in APPROVALS.json. The placeholder intentionally prevents startup.
4. Record Steve's actual approval timestamp with timezone in approved_at, using the human-authorized record. The proposed null is deliberately not a fabricated timestamp. Keep approved_by as ["steve"] and pending_second_approver as "nate" until Nate actually approves. This is a one-human bootstrap exception, NOT completed two-human approval.
5. Run the offline checks and enable repository protections before closing the foundation.

Never rotate BOOTSTRAP_SHA256 for a later rules revision. It pins this initial file only. Whitespace-only file edits also need approval because hashing uses raw bytes. Freeze line endings for this file in the checkout/deployment process; a different checkout hash must fail closed, not silently gain another bootstrap exception.

## Later changes

The human change author opens a review request. Another distinct human independently reviews the exact rules digest. Record two distinct IDs from steve, nate, will in approved_by, the exact sha256, an actual timezone-aware approved_at and a meaningful note identifying the author and review evidence. At least one approver must not be the author. The loader checks two distinct known IDs; it cannot authenticate identities, establish authorship or prove that a review occurred. Those are repository-review responsibilities. Never add a name merely because this proposal mentions it. Preserve prior entries as history; add a new non-bootstrap entry for each new approved digest.

The users table is authoritative; app.rules.HUMANS deliberately mirrors its fixed IDs without opening a database at import. A users-list change requires coordinated human review of the validator.

## Repository enforcement required from Steve

The relay and agents may propose changes, not approve or commit protected foundation files. JSON names are an audit record, not signatures or an access-control boundary. A writer who can alter both the ledger and validator could bypass local checks. Protect /rules/, /app/rules.py, /tests/test_rules.py, /.github/CODEOWNERS, CI configuration, and the importing modules from unauthorized direct writes and bypasses. Review changes that might remove the imports, weaken the check, change composition/export logic or alter the bootstrap pin.

Proposed CODEOWNERS lines (replace placeholders with verified GitHub human handles; users-table IDs are not proof of GitHub handles):

    /rules/ @STEVE_GITHUB_HANDLE @NATE_GITHUB_HANDLE
    /app/rules.py @STEVE_GITHUB_HANDLE @NATE_GITHUB_HANDLE
    /tests/test_rules.py @STEVE_GITHUB_HANDLE @NATE_GITHUB_HANDLE
    /app/agent_conduit.py @STEVE_GITHUB_HANDLE @NATE_GITHUB_HANDLE
    /app/astra_chat.py @STEVE_GITHUB_HANDLE @NATE_GITHUB_HANDLE
    /app/api_budget.py @STEVE_GITHUB_HANDLE @NATE_GITHUB_HANDLE
    /app/astra_agents.py @STEVE_GITHUB_HANDLE @NATE_GITHUB_HANDLE
    /app/astra_tree.py @STEVE_GITHUB_HANDLE @NATE_GITHUB_HANDLE
    /.github/ @STEVE_GITHUB_HANDLE @NATE_GITHUB_HANDLE

Merge these into the existing CODEOWNERS file; later matching patterns take precedence. CODEOWNERS alone neither blocks pushes nor requires both listed owners. Steve must configure protected branches/rulesets: required pull requests, appropriate independent human reviews, code-owner review, dismissal of stale reviews, approval of the latest push by someone other than its pusher, required offline rules checks, no unauthorized bypass and no direct agent/relay writes or merge credentials. Set the required review count to match the agreed two-human policy; do not treat two names in JSON as proof of authenticated approval. Ensure deployment consumes the protected revision. GitHub review settings alone do not restrict local working-tree edits; use restricted credentials and filesystem permissions where that boundary matters.

## Offline checks

After filling bootstrap metadata: python -m unittest discover -s tests -p test_rules.py

Require that command as a protected CI status check in the existing workflow. Importing any migrated module imports app.rules and fails closed for an unapproved changed file. This proposal does not claim that the repository's unseen build system already runs this command.
