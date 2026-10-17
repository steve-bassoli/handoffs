# Ticket-flow acceptance

## Flow evidence

On a ticket page, the renderer receives lineage and full detail data for each lineage item. It presents the MEDIUM root above its three LOW children using authoritative `parent_id` links. Every card shows its ticket ID and is keyboard-operable for navigation.

## Metadata and current position

Each ticket card exposes complexity, status, and assignment in `.flow-meta`. Assignment is displayed only when a `followup_confirmed` event provides `data.assigned_agent`; otherwise it says `Unknown`. The current ticket has `.is-current` and the textual label `You are here`.

## Safety and resilience

Ticket text is inserted with `textContent`, not HTML parsing. A malformed cyclic lineage must render a bounded result rather than recurse forever.

## Proposed relay checks

1. Run `pytest -q tests/test_ticket_flow.py`.
2. Open the MEDIUM ticket and each LOW ticket at desktop and narrow mobile widths.
3. Tab to every flow card; confirm Enter/Space activation follows the card ticket ID.
4. Confirm visible text, not colour alone, identifies the current ticket and the MEDIUM-to-LOW relationship.
