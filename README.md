# Residual Live

Real-time royalty obligation tracking for film & series exploitation.
Event stream (Confluent Cloud) is continuously checked against contract terms —
when a threshold tips, a quantified obligation with the cited clause and a
ready-to-approve settlement notice is created for human sign-off.

Stack: Google ADK · Confluent Cloud · IBM Bob

---

## 1. Overview

In film and television distribution, royalty obligations legally arise the instant a title is streamed, yet settlement occurs in opaque batch cycles 60–90 days later. **Residual Live** solves this by establishing a real-time clearing and settlement nervous system:

1. Streaming events are consumed continuously from **Confluent Cloud** (`demo-events` topic).
2. A deterministic contract engine evaluates cumulative usage against contractual milestones and escalators.
3. Upon reaching contractual thresholds (e.g., 5,000,000 stream minutes under SAG-AFTRA terms), **Google ADK agents** extract and verify the precise clause terms.
4. An immutable 3-tier SHA-256 cryptographic audit chain seals the event history, chain hash, and notice fingerprint.
5. The quantified obligation is published back to Confluent Cloud (`obligations` topic) and presented on an **IBM Carbon** dashboard for human sign-off.

---

## 2. Architecture

```
                                  CONFLUENT CLOUD
                        ┌─────────────────────────────────┐
                        │  topic: demo-events             │
                        └──────────────┬──────────────────┘
                                       │
                                       ▼
                     confluent_client.ConfluentConsumerThread
                                       │
                                       ▼
                            engine.RoyaltyEngine
                  ┌─────────────────────────────────────┐
                  │ • Cumulative minutes / play counts  │
                  │ • Threshold detection               │
                  │ • 3-Tier SHA-256 Cryptographic Chain │
                  └──────────────┬──────────────────────┘
                                 │
                 Threshold Breach / Hero Moment
                                 │
                                 ▼
                     agents.ContractAgentSuite (Google ADK)
                  ┌─────────────────────────────────────┐
                  │ • Contract Intake Agent             │
                  │ • Clause Verification Agent         │
                  │ • Settlement Notice Writer Agent    │
                  └──────────────┬──────────────────────┘
                                 │
                                 ▼
                     confluent_client.ObligationsProducer
                        ┌─────────────────────────────────┐
                        │  topic: obligations             │
                        └──────────────┬──────────────────┘
                                       │
                                       ▼
                       FastAPI + WebSocket Live UI (Carbon)
                        ┌─────────────────────────────────┐
                        │  Human-in-the-Loop 1-Click Sign │
                        └─────────────────────────────────┘
```

- **Google ADK Agents (`residual_live/agents.py`):**
  - *Contract Intake Agent:* Extracts structured payout rules and milestones from legal agreements (e.g., SAG-AFTRA sample contract terms).
  - *Clause Cross-Check Agent:* Validates computed settlements against specific agreement clauses, verifying milestone eligibility.
  - *Notice Writer Agent:* Formulates quantified, legally cited settlement notices.
  - Built using Google Agent Development Kit (`google-adk`, `LlmAgent`, `Runner`, and Gemini models).

- **Deterministic Royalty Engine (`residual_live/engine.py`):**
  - Manages contract models, multi-title streaming portfolios, escalators, and threshold milestones.
  - Enforces a 3-tier cryptographic audit chain: individual event entry hashing, chain-linked audit logs, and immutable notice fingerprints.

- **Bidirectional Confluent Cloud Streaming (`residual_live/confluent_client.py`):**
  - Consumer thread continuously ingests high-throughput streaming events from `demo-events`.
  - Producer thread streams finalized, verified settlement notices out to `obligations`.

- **Web Service & Dashboard (`residual_live/app.py`, `residual_live/static/`):**
  - FastAPI backend providing REST endpoints and a real-time bidirectional WebSocket feed (`/ws`).
  - Single-page dashboard styled according to the **IBM Carbon Design System** (Light / g10 Theme).

---

## 3. Run Instructions

### Prerequisites
- Python 3.10 or higher
- Confluent Cloud Kafka cluster credentials
- Google Gemini API key

### Installation

Clone the repository and install dependencies with [`uv`](https://docs.astral.sh/uv/) or standard `pip`:

```bash
# Using uv (recommended)
uv sync

# Or using pip in a virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Environment Variables

Configure the following environment variables in a `.env` file or export them in your shell:

| Variable | Required | Description |
|---|---|---|
| `CONFLUENT_BOOTSTRAP` | Yes | Confluent Cloud Kafka bootstrap server endpoint |
| `CONFLUENT_API_KEY` | Yes | Confluent Cloud cluster API key |
| `CONFLUENT_API_SECRET` | Yes | Confluent Cloud cluster API secret |
| `CONFLUENT_TOPIC` | No | Inbound stream topic (default: `demo-events`) |
| `CONFLUENT_OBLIGATIONS_TOPIC` | No | Outbound obligations topic (default: `obligations`) |
| `CONFLUENT_GROUP_ID` | No | Kafka consumer group ID (default: `residual-live-group`) |
| `GEMINI_API_KEY` | Yes | Google Gemini API key for ADK agents |
| `GEMINI_MODEL` | No | Gemini model name (default: `gemini-3.1-pro-preview`) |
| `DEMO_KEY` | No | Authorization key for state-mutating actions |
| `HOST` | No | Server host (default: `0.0.0.0`) |
| `PORT` | No | Server port (default: `8000`) |

> **Note on Stream Integrity:** Confluent Cloud connectivity is verified on startup. Without valid credentials, the application will fail fast by design rather than running unverified mock loops.

### Running the Application

Start the local server with Uvicorn:

```bash
# Using uv
uv run uvicorn residual_live.app:app --host 0.0.0.0 --port 8000

# Or directly with python
python3 -m uvicorn residual_live.app:app --host 0.0.0.0 --port 8000
```

Once running, navigate to `http://127.0.0.1:8000/` in your browser.

### Running Tests

Execute the automated test suite with pytest:

```bash
uv run pytest
```

All 90 unit and integration tests validate engine calculations, cryptographic hashing integrity, multi-title isolation, and API security.

---

## 4. Live Demo

A production deployment is accessible for judges at:

**[https://residual.millerandmuller.com](https://residual.millerandmuller.com)**

To test state-mutating actions (Next Demo Event, 1-Click Approval, Reset, Intake), judges can use the authorization key provided in the Devpost submission notes:
- Either append `#key=<DEMO_KEY>` to the URL,
- Or click **🔑 Set Demo Key** in the top banner.

---

## 5. Built with IBM Bob

Core schemas (`RoyaltyEvent`, `ContractRule`, `SettlementNotice`), cryptographic chain hashing layers, and clause test corpora were developed under **IBM Bob** (watsonx Code Assistant).

Audit logs, task identifiers, and coin consumption ledgers are tracked in [`bob-runs/`](./bob-runs/) and exposed live via the `/api/bob-audit` endpoint and the in-app **IBM Bob Governance** inspector.

---

## 6. License

This project is licensed under the [MIT License](./LICENSE) — see the LICENSE file for details.
