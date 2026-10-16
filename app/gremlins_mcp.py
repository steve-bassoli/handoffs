"""Read-only stdio MCP for synthetic Gremlins comparisons; no backend execution."""
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from app.gremlins import compare, sabotage, witness

server = FastMCP('gremlins', instructions=(
    'Mimic compares supplied legacy/REST/MCP observations with an independent expected contract. '
    'Saboteur changes only a private synthetic copy to prove defect detection. Witness returns a hashed report '
    'and named quirk record. SIM only: no Watson, Oracle, filesystem, HTTP or AI calls, and no bounty creation. '
    'Never provide secrets or production records. Supplied observations are claims, not proof of backend execution.'))
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


def checked(operation, payload):
    try:
        return operation(payload)
    except (ValueError, TypeError):
        raise ValueError('Use a focused SIM comparison with a case contract and legacy/rest/mcp observations; no live records') from None


@server.tool(annotations=READ)
def mimic(payload: dict[str, Any]) -> dict[str, Any]:
    """Compare the three supplied synthetic observations against explicit expected behavior."""
    return checked(compare, payload)


@server.tool(annotations=READ)
def saboteur(payload: dict[str, Any]) -> dict[str, Any]:
    """Prove a passing synthetic comparison catches a private injected mismatch; change nothing external."""
    return checked(sabotage, payload)


@server.tool(annotations=READ)
def witness_report(payload: dict[str, Any]) -> dict[str, Any]:
    """Return one portable hashed observation report, quirk preservation rule and draft discrepancy question."""
    return checked(witness, payload)


if __name__ == '__main__':
    server.run(transport='stdio')
