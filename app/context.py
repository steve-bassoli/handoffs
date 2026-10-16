"""Project readable requirements without changing the preserved legacy packet."""
import re


def legacy_requirements(context):
    sections = {}
    heading = None
    for line in context.splitlines():
        match = re.match(r'^##\s+(.+?)\s*$', line)
        if match:
            heading = match[1].casefold()
            sections[heading] = []
        elif heading:
            sections[heading].append(line)
    goal = '\n'.join(sections.get('goal', [])).strip()
    criteria = []
    for line in sections.get('acceptance criteria', []):
        match = re.match(r'^\s*(?:[-*]|\d+[.)])\s+(.+)', line)
        if match:
            criteria.append(match[1])
        elif line.strip() and criteria:
            criteria[-1] += '\n' + line.strip()
    return goal, criteria


def project_legacy(bounty):
    legacy = bounty['legacy']
    if not legacy:
        return
    goal, criteria = legacy_requirements(legacy['context'])
    if bounty['goal'] == 'Historical imported assignment' and goal:
        bounty['goal'] = goal
    if not bounty['criteria'] and criteria:
        bounty['criteria'] = criteria
    if not bounty['repository']:
        bounty['repository'] = legacy['source'].removeprefix('git:')
