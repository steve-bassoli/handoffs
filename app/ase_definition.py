"""Proposed ASE definition; no repository inspection or external verification."""


def build_definition():
    """Return independent ASE-v1 data without I/O or shared mutable values."""
    source_hash = '24c95d2581a9e91e46b0c9ed4500a10631971cca3f05a34e6b7dc3582aff3e73'

    def citation(identifier, url, summary, status):
        return {
            'id': identifier,
            'url': url,
            'summary': summary,
            'status': status,
            'provenance': {
                'source': 'ase_sources',
                'sha256': source_hash,
                'external_reviewed': False,
            },
        }

    return {
        'schema_version': 'ASE-v1',
        'definition': (
            'An Auditable Self-improving Ecosystem (ASE) is a proposed community '
            'pattern in which people and agents propose, evaluate and record '
            'improvements under explicit human authority and resource limits.'
        ),
        'properties': [
            {
                'id': 'human-authority',
                'text': 'Human approval gates govern integration; automation does not establish human acceptance.',
                'status': 'proposed',
            },
            {
                'id': 'auditable-change',
                'text': 'Record proposed changes, evaluation evidence, attribution and unresolved failures before promotion.',
                'status': 'proposed',
            },
            {
                'id': 'bounded-resources',
                'text': 'Respect authorized budgets, consent and stop boundaries; unknown usage retains its reservation.',
                'status': 'proposed',
            },
            {
                'id': 'tested-learning',
                'text': 'Treat improvement as a claim requiring evaluation, not a consequence of self-modification alone.',
                'status': 'proposed',
            },
        ],
        'prior_work': [
            citation(
                'self-evolving-survey',
                'https://arxiv.org/pdf/2508.07407',
                'The pinned source describes a 2025 survey calling for agents that live, learn and last.',
                'not_independently_reviewed',
            ),
            citation(
                'darwin-godel-machine',
                'https://arxiv.org/pdf/2505.22954',
                'The pinned source describes an archive of coding agents, code edits and benchmark evaluation, with oversight and reward-hacking cautions.',
                'not_independently_reviewed',
            ),
            citation(
                'unnamed-reference-kit',
                None,
                'The pinned source mentions a reference kit without a traceable URL; it is not supporting evidence.',
                'unavailable',
            ),
        ],
        'limits': [
            'External references were not independently reviewed here; the source hash identifies consulted shelf content, not article verification.',
            'Properties describe a proposed pattern, not observed repository conformance or proven improvement capabilities.',
            'No first-of-its-kind or superiority claim is established; citation-dependent novelty criteria remain blocked.',
            'Repository-generated conformance requires separately inspected implementation and recorded checks; this definition alone supplies neither.',
        ],
    }
