# Breaking Bad Bank: Ozark’s Slightly Less Suspicious Cousin

A conversational hackathon demo of an agentic AML (Anti-Money Laundering) alert investigation. The prototype combines MCP tool calls, deterministic Python risk rules, AI-assisted evidence summaries, and an analyst approval step.

> Inspired by the money-laundering drama in *Ozark*. The show is fiction; this project uses mock data and is for demonstration only.

## What this demo does

An analyst selects an alert and starts an investigation. The app retrieves mock customer and transaction data through MCP tools, screens counterparties against a tiny local demo list, calculates a risk score with explicit Python rules, and displays the evidence and next step. An LLM can help write the investigation summary and draft SAR narrative, but it does not calculate the score or choose the action.

| Example alert | Demo behavior |
| --- | --- |
| `ALERT-A` | Low score; auto-dismiss path with an audit entry. |
| `ALERT-B` | Cash deposits just below $10,000; analyst case and notification path. |
| `ALERT-C` | High score of 85; recommendation pauses for analyst approval. Approval creates a mock SAR record. |

The app shows the collected evidence, deterministic rule hits, investigation summary, action state, and a trace of tool and workflow steps.

## Quick start

### Requirements

- Python 3.11 or newer
- A terminal that can run the commands below
- Astra-compatible API credentials only if you want live LLM-generated prose; the demo falls back to local templates without them

### Install

From the project folder, create and activate a virtual environment, then install dependencies:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` if you want to configure the optional LLM endpoint. Fill in `ASTRA_API_KEY`, `ASTRA_BASE_URL`, and `ASTRA_MODEL`. Keep `.env` private; it is ignored by Git. Locally, `MCP_MODE=http` is the default and `MCP_URL` points to the separately running mock server.

### Run

Open two terminals in the project folder and activate the virtual environment in each.

Terminal 1 — start the local MCP server:

```powershell
python mcp_server.py
```

Terminal 2 — start the Streamlit app:

```powershell
streamlit run app.py
```

Open the local URL printed by Streamlit (typically `http://localhost:8501`). The MCP server listens at `http://127.0.0.1:8000/mcp`.

## Three-minute demo talk track

“Before I show the prototype, let’s quickly understand what AML means. **AML stands for Anti-Money Laundering.** It’s the work banks do to spot activity that might be connected to money from crime, and to decide what needs a closer look. A single unusual transaction doesn’t prove anything—it’s a signal for an analyst to investigate.

If you’ve watched *Ozark*, you’ve seen the dramatic version of money laundering: criminals try to make illegal money look like it came from a normal business. In real life, banks use monitoring systems to spot patterns and raise alerts. Our prototype shows how an AI-assisted system could help an analyst investigate those alerts.

Here’s the alert queue. Each alert represents activity that a bank’s monitoring rules have flagged. I’ll start with **ALERT-A**. The system collects the customer and transaction details, checks the counterparty, and applies clear, deterministic rules to calculate a risk score. The AI helps write a readable summary, but it doesn’t decide the score or choose what action to take.

Now let’s look at **ALERT-B**. This one shows several cash deposits just below $10,000. A sequence like that can be a reason to investigate further. The system identifies the pattern and creates an analyst case. That’s a useful example of AI helping people find the important evidence without making the final call.

Finally, **ALERT-C**. We have a large international wire and screening matches, so the rules produce a higher score. The system recommends further action and pauses for human approval. The analyst can review the evidence and summary before deciding what to do. The recommendation is not the same as proof of wrongdoing.

The main idea is that AI can help gather information and explain why an alert was raised, while clear rules and human review keep important decisions understandable. This is a hackathon demo with mock data—not a real bank screening system.”

## Technical overview

### Why it is agentic

The prototype does more than answer a prompt with text. Given an alert ID, the Python orchestrator follows a multi-step workflow: it fetches evidence through tools, uses the returned records in later steps, evaluates deterministic rules, and branches into different actions based on the score. It maintains workflow state for high-risk alerts so an analyst can approve or reject the recommendation.

Its autonomy is bounded. Low-risk alerts follow the configured auto-dismiss path, medium-risk alerts create a case, and high-risk alerts pause for a human decision. The LLM is used for prose generation only; it does not select tools, determine risk scores, or approve actions.

### MCP and the workflow

**MCP (Model Context Protocol)** provides a standard way for the orchestrator to discover and call tools exposed by the local FastMCP server. In this demo, those tools are mock integrations for retrieving alerts, customers, and transactions, screening entities, creating cases, recording approvals, filing a mock SAR, and logging audit events.

The main investigation flow is:

1. Streamlit sends the selected alert ID to `AgentOrchestrator`.
2. The orchestrator calls MCP tools to retrieve alert, customer, transaction, and screening evidence.
3. Deterministic Python rules calculate the score and select a workflow branch.
4. The LLM client drafts a factual summary from the collected evidence, or uses a local template if the endpoint is not configured or fails.
5. The app presents the outcome and trace. For a high-risk alert, it waits for the analyst’s explicit approval or rejection.
6. After approval, the demo generates a SAR narrative and records a mock filing through an MCP tool.

### Local and hosted MCP modes

The default `MCP_MODE=http` connects to the separately started MCP server at `MCP_URL`, which is useful for showing two distinct local processes. For a single-service host such as Streamlit Community Cloud, set `MCP_MODE=inprocess`. The app then uses FastMCP's in-memory transport to call the same MCP tool server inside the Streamlit process. This keeps MCP tool discovery and calls in the demo while removing the cloud app's dependency on a server running on your laptop.

## Publish a public web app

The simplest hosting option for this Streamlit demo is [Streamlit Community Cloud](https://share.streamlit.io/). The repository must contain `app.py`, `requirements.txt`, the Python modules, `data.json`, and `.streamlit/config.toml` at the expected paths. Community Cloud installs packages from `requirements.txt` and lets you choose the app's Python version in deployment settings.

1. Sign in at [share.streamlit.io](https://share.streamlit.io/) and connect your GitHub account if prompted.
2. Choose **Create app** and select the public `ozark-aml-agent-demo` repository, branch `main`, and entrypoint `app.py`.
3. In **Advanced settings**, select Python 3.12.
4. In the Secrets field, add this setting so the cloud deployment uses its in-process MCP mode:

   ```toml
   MCP_MODE = "inprocess"
   ```

   Astra credentials are optional. Without them, the app uses its template-generated summary. If you want LLM prose, add `ASTRA_API_KEY`, `ASTRA_BASE_URL`, and `ASTRA_MODEL` here; never commit credentials to GitHub.

5. Click **Deploy**. After the app starts, copy the `*.streamlit.app` URL from the app page and share it with your demo users. Later commits pushed to the selected GitHub branch are used to update the app.

This is a public demo link, not a production AML service. Anyone with the URL can use the mock alert workflow, including its simulated approval and SAR actions. Do not put real customer or transaction data in the app. The hosted process and its local audit file may reset; this prototype does not provide durable multi-user storage or user authentication.

## Risk rules in this prototype

The scoring logic is in `orchestrator.py` and is intentionally easy to inspect:

- A single transaction greater than $100,000: **+25**
- Counterparty linked to a demo sanctioned country: **+30**
- Counterparty name on the demo PEP list: **+30**
- Three or more cash deposits of $8,000–$9,999 within seven days: **+35**
- Total observed activity greater than five times declared annual income: **+15**

The score is capped at 100. The configured branches are under 30 (human-out), 30–70 (human-on), and above 70 (human-in). These thresholds and lists are toy examples for the demo, not validated AML controls.

## High-level file guide

| File or folder | Purpose |
| --- | --- |
| `app.py` | Streamlit user interface: alert queue, customer and transaction details, investigation outcome, approval controls, SAR draft, and agent trace. |
| `orchestrator.py` | Sequences investigation steps, calls MCP tools, calculates deterministic scores, and manages approval and rejection flows. |
| `mcp_server.py` | Local FastMCP HTTP server that exposes mock banking, screening, case, approval, SAR, notification, and audit tools. |
| `mcp_client.py` | Small synchronous wrapper used by the orchestrator to call the asynchronous FastMCP client. |
| `llm_client.py` | Optional Astra/OpenAI-compatible text generation for summaries and SAR drafts, with template fallback and a heuristic output check. |
| `data.json` | Mock alerts, customer profiles, transactions, and small screening lists used by the demo. |
| `models.py` | Shared Pydantic data models for alerts, customers, transactions, and trace steps. |
| `requirements.txt` | Pinned Python package dependencies. |
| `.env.example` | Names and example defaults for local environment variables. Copy to `.env` for private configuration. |
| `.streamlit/config.toml` | Project-level Streamlit settings; usage statistics are disabled. |
| `.gitignore` | Excludes local secrets, virtual environments, Python caches, audit data, and logs from Git. |
| `README.md` | Project setup, demo script, technical explanation, limitations, and file guide. |
| `.venv/` | Local Python environment created during setup; do not upload it. |
| `__pycache__/` | Python-generated bytecode cache; do not upload it. |
| `audit.db` | Local SQLite audit events generated at runtime; do not upload it. |
| `streamlit*.log`, `streamlit*.err` | Local server logs; do not upload them. |

## Project structure

```text
aml-agent-demo/
├── app.py
├── orchestrator.py
├── mcp_client.py
├── mcp_server.py
├── llm_client.py
├── models.py
├── data.json
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
└── .streamlit/
    └── config.toml
```

Local-only files such as `.env`, `.venv/`, `audit.db`, caches, and logs are intentionally omitted from this structure.

## Limitations and safety boundaries

- The records and screening lists are mock data. No external banking, payment, or sanctions systems are contacted.
- Screening is exact matching against tiny hardcoded demo lists; it is not real sanctions or PEP screening.
- Risk scoring is a simplified illustration, not a validated AML model. A score or match is not proof of misconduct.
- The LLM writes prose only. The fallback and heuristic output check are demo safeguards, not a guarantee against hallucinations.
- Approval, audit, case, and SAR behavior are simulated. A SAR narrative is a draft, and “filed” means a mock record was created—not that a report was submitted to a regulator.
- The audit log is stored locally in `audit.db`; some workflow state is in memory and resets when the MCP server restarts.
- Do not use this prototype to make real compliance or customer decisions, or with real personal or financial data.

## Uploading this project to GitHub

### Option 1: GitHub website

1. Sign in to GitHub and create a new repository. A fun title is **Breaking Bad Bank: Ozark’s Slightly Less Suspicious Cousin**; a URL-friendly name could be `ozark-aml-agent-demo`.
2. For the simplest upload, create the repository without adding a README, license, or `.gitignore` on GitHub; this project already has a README and `.gitignore`.
3. In the new repository, choose **Add file → Upload files**.
4. Upload the project’s source files and the `.streamlit/config.toml` file. Do not upload `.env`, `.venv/`, `audit.db`, `__pycache__/`, or any `streamlit*.log` / `streamlit*.err` files.
5. Commit the upload in GitHub.

### Option 2: Git from PowerShell

Install Git if needed, then run these commands from the project folder. Create an empty GitHub repository first and replace the URL below with its HTTPS or SSH URL.

```powershell
git init
git add README.md .gitignore .env.example requirements.txt app.py orchestrator.py mcp_client.py mcp_server.py llm_client.py models.py data.json .streamlit/config.toml
git status
```

Review `git status` and confirm there is no `.env`, `.venv`, `audit.db`, or log file staged. Then commit and connect the GitHub repository:

```powershell
git commit -m "Add AML agent demo prototype"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
git push -u origin main
```

If GitHub asks you to authenticate, use its recommended browser sign-in or a configured SSH key. Never put an API key, password, or personal access token directly into the remote URL or a committed file.

## License

No license is included yet. Add a license file if you want to specify how others may use, modify, and redistribute the project.
