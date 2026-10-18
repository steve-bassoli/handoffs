"""Read-only effect descriptions, never execution permission.

Keys must come from server dispatch, not request metadata. Compound effects
must not be reduced to a reversible constituent. Unknown inputs fail closed.
Construction bypasses do not change classifications or establish human assent.
"""
from types import MappingProxyType


def _row(reversibility, gate, reason):
    return MappingProxyType(dict(reversibility=reversibility, gate=gate, reason=reason))


_UNKNOWN = _row('irreversible', 'human required',
                'Unknown or mixed effects retain every applicable protection; no execution authority.')

# One authoritative action table. Entries describe requirements, not proof that
# a downstream executor implements them. Unverified service effects fail closed.
EFFECTS = MappingProxyType({
    'internal_work': _row('reversible', 'Existing source/resource authorization; audit', 'Internal code, tests, prototypes and drafts only; excludes deployment, rules and real data.'),
    'post': _row('reversible', 'Existing ownership, intake and reservation rules; audit', 'Internal task draft only; no authority for consequential downstream effects.'),
    'edit': _row('reversible', 'Existing ownership, intake and reservation rules; audit', 'Internal task edit only; no authority for consequential downstream effects.'),
    'take': _row('reversible', 'Own authorized identity and existing allocation; audit', 'Voluntary work only; no inferred acceptance or fresh budget.'),
    'release': _row('reversible', 'Own authorized identity and existing allocation; audit', 'Voluntary work release, not publication; no release route verified on this shelf.'),
    'administrative_close': _row('irreversible', 'human required', 'Reversible only after domain evidence establishes no acceptance or participant effects; not verified here.'),
    'intake_screened': _row('reversible', 'Audit assessment; preserve blockers', 'Assessment never authorizes overriding its veto.'),
    'intake_override': _row('irreversible', 'Signed-in human; current-text binding and note', 'Human-owned exception grants no later release, data or spending authority.'),
    'intake_overridden': _row('irreversible', 'Signed-in human; current-text binding and note', 'Recorded override effect retains the same protection as its command.'),
    'close_human': _row('irreversible', 'Authorized human; claimant rules and proof', 'Closure cannot erase attributed acceptance or imply acceptance for someone else.'),
    'proof_human': _row('irreversible', 'Authorized human; existing proof workflow', 'Human proof attribution is consequential; construction provenance must remain explicit.'),
    'ai_proof_human': _row('irreversible', 'Authorized human; existing proof workflow', 'Actual service dispatch key for proof-human; never infer human assent from construction bypasses.'),
    'signoff.request': _row('reversible', 'Authenticated authorized request; audit', 'A request neither grants nor executes permission; demo headers are insufficient in the observed ledger.'),
    'signoff.decision': _row('irreversible', 'Human authority; exact item and recommendation state', 'Observed ledger records human or prototype-auto provenance; it does not verify displayed recommendation state or two-human approval.'),
    'signoff.consume': _row('irreversible', 'Exact payload, unused approval, provenance and required count', 'Observed helper binds payload and consumes once in the caller transaction; two-human enforcement is not established.'),
    'publish': _row('irreversible', 'Scoped human authorization before exposure', 'Withdrawal cannot undo disclosure; ledger presence does not prove executor enforcement.'),
    'automation_mode': _row('irreversible', 'Human authority; two humans for operative rule changes', 'An undoable setting can enable irreversible effects.'),
    'spend_ceiling': _row('irreversible', 'Explicit human budget authority within hard limits', 'Cannot create funds, spend protected reserves or duplicate child allocations.'),
    'real_spending': _row('irreversible', 'Explicit allocation, accounting and reservations', 'Unknown usage retains its reservation; allocation is not new spending authority.'),
    'price_checkpoint': _row('irreversible', 'Retain protected-action gate pending executor evidence', 'Action name alone does not establish its effects.'),
    'rule_texts': _row('irreversible', 'Two distinct authenticated humans; same effective change', 'Protected even during construction; read-only here and excluded from ordinary digest batches.'),
    'watson_real_data': _row('irreversible', 'Scoped human authorization and privacy/access controls', 'Reading can disclose real data; isolated synthetic fixtures are different.'),
    'policy_adoption': _row('irreversible', 'Applicable human authority; two humans for operative rules', 'Drafting is reversible; adoption changes authority or consequences.'),
    'attach_package': _UNKNOWN,
    'ai_reopen': _UNKNOWN,
    'checkpoint': _UNKNOWN,
    'status': _UNKNOWN,
    'deliver': _UNKNOWN,
    'settle': _UNKNOWN,
    'cancel': _UNKNOWN,
    'review': _UNKNOWN,
    'accept': _UNKNOWN,
    'ai_start': _UNKNOWN,
    'ai_answer': _UNKNOWN,
    'ai_retry': _UNKNOWN,
    'ai_confirm': _UNKNOWN,
    'ai_complete': _UNKNOWN,
    'ai_proof_attach': _UNKNOWN,
    'ai_proof_queue': _UNKNOWN,
    'ai_proof_complete': _UNKNOWN,
    'ai_profile': _UNKNOWN,
    'ai_dependencies': _UNKNOWN,
})


def classify(action):
    """Return a detached description for an exact server-owned action key.

    Request objects, sequences and mixed-effect composites are not action keys.
    No client tag, payload field, header or construction flag is consulted.
    """
    row = EFFECTS.get(action, _UNKNOWN) if type(action) is str else _UNKNOWN
    return dict(row)


def gate_for(action):
    return classify(action)['gate']


def effect_table():
    """Return a detached JSON-ready snapshot, never mutable backing state."""
    return {action: dict(row) for action, row in EFFECTS.items()}
