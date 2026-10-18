# Dashboard shell integration

The local deferred `dashboard-live.js` script creates `window.dashboard` for
`#dashboard`. Without host configuration it displays the fixed live, flow and
ops slots but makes no requests. The host must supply `window.dashboardConfig`
before the deferred script executes, with an explicit same-origin `endpoint`
and authorized `headers` where required. Session credentials use same-origin
fetch credentials. Never put credentials in a URL or guess a demo identity.
The proposed endpoint is `/api/dashboard/live`; this change does not add that
route or establish production authentication. The v1 response shape remains
the contract in `dashboard_live_contract.md`.

The controller is also available as `window.createDashboard(root, options)`.
Destroy an existing instance before creating another for the same root.
Call `window.dashboard.register('flow', renderer)` or register `live` / `ops`
to extend a slot. Renderers receive `(element, snapshot, viewState)` immediately
and on updates. Use stable interactive elements and update text with
`textContent`; replacing focused nodes inside an extension can lose focus.
The shell's pause and resume buttons remain stable across refreshes.

Polling starts immediately when configured, then waits 2.5 seconds after each
settlement. Hidden tabs wait at least 10 seconds; visibility changes reschedule
an outstanding timer without starting a second request. Read failures back off
to 60 seconds. A 401 or 403 stops that instance permanently; restoring an
authorized session requires host reinitialization. Pause retains observations,
and destroy discards late responses and removes listeners. A pending request
holds the single-flight slot; there is no request timeout or age-based stale
policy. Last-good data is labeled stale after failure or while paused.

Local receipt time and reported activity do not establish agent liveness.
Source status and source event time remain visible separately. No spending,
mode changes, or agent controls are provided.
