# Ledger safeguards and independent verification

The Commons should make abuse harder to carry out and easier for participants to
challenge. Blockchain may help witness history across independent operators; it
does not establish consent, fairness or incorruptibility. Participant protections
must not depend on owning cryptocurrency, paying network fees or surrendering
private information.

## Protection boundaries

Owner authorization, protected reserves and independent evidence solve different
problems. Authenticated transaction consent and an isolated ledger authority must
prevent unauthorized debits. Independently retained checkpoints can expose changes
to previously witnessed records. Neither a blockchain nor a valid hash proves
that a recorded action was legitimate or that the operator will remain available.
The constitution's no-debt, no-punishment and voluntary-participation rules remain
unchanged. No maintainer, sponsor, wealthy participant or AI receives a resource
confiscation power.

The current demo has simulated identity, monthly Gold allocations and no positive
reserve enforcement. Those gaps remain. This checkpoint tool does not certify
economic protection, owner consent, balance correctness or human presence.

## Offline checkpoint foundation

`app.ledger_checkpoints` provides a read-only commitment to an exact SQLite ledger
snapshot and the exact policy file supplied by the operator. It covers accounts,
Gold transactions, Gold entries and monthly allocations in deterministic order
within one read transaction. It does not cover opportunity evidence, identity
provider records or the rest of the database.

The versioned projection is limited to `accounts(id,user_id,kind)`,
`gold_transactions(id,kind,bounty_id,created_at)`,
`gold_entries(seq,transaction_id,account_id,amount)` and
`monthly_allocations(user_id,month,gold)`. New columns are not automatically
protected. Row insertion order and SQLite file layout are not economic history;
the named values and deterministic key order define the comparison.

A cryptographically random private nonce blinds the snapshot commitment; the
checkpoint binds the nonce, an explicit ledger identifier, a format version and
the policy digest. Keep the complete checkpoint in private, independently
controlled storage. The tool prints no ledger rows, but checkpoint identifiers,
policy digests and comparison results can still reveal information. Do not
automatically publish them.

From the repository root, using an explicitly authorized isolated database:

```powershell
# Save stdout through an approved private artifact mechanism, then retain a copy
# outside the ledger operator's control. Do not use the live database by default.
.venv/Scripts/python.exe -B -m app.ledger_checkpoints export `
  --database C:/approved-test/ledger.sqlite --log-id test-ledger `
  --policy-file PLAN/EMPOWERMENT_CONSTITUTION.md

.venv/Scripts/python.exe -B -m app.ledger_checkpoints verify `
  --database C:/approved-test/ledger.sqlite --log-id test-ledger `
  --policy-file PLAN/EMPOWERMENT_CONSTITUTION.md `
  --checkpoint-file C:/independently-retained/checkpoint.json
```

Export creates an **unwitnessed** checkpoint; it does not establish its own trust.
Verification requires an explicit supplied checkpoint and expected ledger ID.
A match means `MATCHES_SUPPLIED_CHECKPOINT_NOT_AUTHENTICATED`, not authorization
or blockchain finality. Exit 0 means a match, 1 means a different snapshot and 2
means the check could not be completed. Replacing both the database and the
checkpoint can fool local comparison: independence of checkpoint custody is the
essential trust assumption.

This is an exact-snapshot comparator, not an append-only log. Legitimate new
transactions also change the commitment. Compare the retained snapshot to its
checkpoint; a later live database is not expected to match. The tool does not
distinguish a legitimate append from a fraudulent append, validate economic
invariants or create a chain of authenticated history. A real deployment needs a
defined snapshot/sequence protocol, witness custody, freshness checks, signed
receipts and independently checked continuity before claiming ongoing coverage.

The tool opens an existing database in read-only mode. It performs no migration,
allocation, transfer, application initialization, network request, blockchain
transaction or automatic anchoring. It does not change wallet behavior and is
not connected to the live API, MCP server or web interface.

## Future blockchain boundary

Use a blockchain only if independently governed witnesses materially improve the
identified operator threat. A private chain whose validators, clients, release
keys and recovery paths are all controlled by the same operator does not remove
unilateral control. Technical validators under one owner are not independent
human oversight. The number and threshold follow the threat model, not RO3.

An eventual anchor should contain only a reviewed opaque aggregate commitment,
never personal records, balances, consent documents, source code, videos, aid
requests or identifying metadata. Do not put raw hashes of low-entropy personal
values on-chain: guessing attacks can reveal them. Keep blinding material and
private proof material off-chain; assess correlation and deletion risks before
any publication. Publication of even a hash is an external disclosure decision.

An anchor receipt would need the expected chain identity, transaction, inclusion
and finality evidence and a binding to the exact witnessed commitment. Verify
these independently rather than trusting an RPC success message. Define fork,
outage, compromise and recovery behavior. A fabricated local receipt or fixture
must never be shown as a real anchor. No blockchain or contract is deployed by
this foundation.

Sponsors, not recipients, would authorize bounded infrastructure costs. No gas
fees, wallet deposits, speculative token or transferable governance power should
be required to receive basic participation. Network failure must not create debt,
silently confiscate resources or erase a person's entitlement. Disputed transfers
should remain unresolved with an explanation and an appeal route; safety checks
are not punishments.

Before external anchoring or independent ledger enforcement, explicitly decide
witness operators and their independence, identity and transaction authorization,
private-data handling, recovery authority, a sustainable sponsor budget and the
reserve/allocation migration policy. Review both collusion and censorship risks.
No rule change may introduce an administrator deduction exception. A valid
checkpoint does not approve a policy amendment or software upgrade.

## Required evidence

The first offline tests must demonstrate exact matching, nonce separation and
detection of changed, missing or added ledger rows, altered account ownership,
different policy bytes and the wrong ledger ID. They must also demonstrate the
negative control: an attacker can recompute a self-consistent checkpoint after
rewriting history, but it does not match the independently retained original.
Tests use disposable ledgers and do not certify a live witness.

Prevention needs separate evidence: real owner-bound consent with replay
protection; atomic reserve checks across every mutation interface; independent
operator controls; and tested recovery, privacy and availability. Do not turn
the checkpoint's passing tests into claims that those controls exist.

## Technical basis

[NIST IR 8202](https://doi.org/10.6028/NIST.IR.8202) describes blockchain as
distributed tamper-evident and tamper-resistant ledger technology and discusses
its governance and immutability limits. The Commons checkpoint is a narrower
local commitment primitive, not an implementation of distributed consensus.
