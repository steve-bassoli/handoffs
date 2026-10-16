# HANDOFFS

Standalone prototype for creating, assigning, tracking, and completing AI-assisted work handoffs.

Requires Python 3.11 or newer. Run these setup commands from the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Start the service:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Check it from another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

The health endpoint returns `{"status":"ok"}`. API documentation is available at <http://127.0.0.1:8000/docs>.

Implementation follows the [prototype plan](PLAN/HANDOFFS_WEBAPP_PLAN.md) and its linked iterative steps. HF-01 provides the service skeleton; bounties, wallets, and the web interface are subsequent steps.
