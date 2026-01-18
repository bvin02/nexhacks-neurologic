# DecisionOS - Project Continuity Copilot

<div align="center">

![DecisionOS](https://img.shields.io/badge/DecisionOS-Turing%20City-00f0ff?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.11+-3776ab?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109-009688?style=for-the-badge&logo=fastapi&logoColor=white)

**The operating system layer for long-running projects.**

*Same model. Same prompt. Only memory changed.*

</div>

---

## What is DecisionOS?

DecisionOS fixes a core failure of stateless LLMs: **they do not remember** why things were decided, what was tried before, or what constraints still apply.

DecisionOS introduces a **persistent cognitive layer** that:

- ✓ Stores durable project memory
- ✓ Governs future responses using that memory
- ✓ Enforces commitments and decisions
- ✓ Detects contradictions and regressions
- ✓ Explains behavior with explicit evidence

**This is not "ChatGPT with memory." This is a continuity operating system for building things.**

---

## Turing City Theme

Built for the **"Turing City"** hackathon theme - a futuristic city where Artificial General Intelligence is widespread.

In Turing City, intelligence is not just generating answers. It is **continuity, governance, and accountability over time**.

---

## Key Features

### 1. Typed Memory System
- **Decisions**: Choices made between alternatives
- **Commitments**: Promises about future behavior
- **Constraints**: Limitations that must be respected
- **Goals**: Objectives to achieve
- **Failures**: What was tried and didn't work
- **Assumptions**: Unstated assumptions made explicit

### 2. Enforcement Engine
Before every response, DecisionOS checks against existing commitments and constraints. If you try to violate a past decision, the system **challenges you with citations**.

### 3. Memory Governance
- Version history for all memories
- Conflict detection between memories
- Deduplication and merging
- Temporal decay and compaction

### 4. Receipts for Everything
Every answer includes debug metadata showing:
- Which memories were used
- Which commitments were checked
- Whether any violations occurred
- Citations to source evidence

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+ (for serving frontend)
- OpenAI API key OR Google Gemini API key

### 1. Clone and Setup

```bash
cd NeuroLogic

# Setup backend
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys
```

### 2. Configure API Keys

Edit `backend/.env`:

```env
# Choose your provider: "openai" or "gemini"
LLM_PROVIDER=openai

# OpenAI
OPENAI_API_KEY=sk-your-key-here

# OR Gemini
GEMINI_API_KEY=your-gemini-key-here
```

### 3. Start Backend

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Start Frontend

```bash
cd frontend
# Using Python's built-in server
python -m http.server 3000

# Or using Node
npx serve -l 3000
```

### 5. Open Browser

Navigate to `http://localhost:3000`


## Architecture

```
┌─────────────────────────────────────┐
│          Frontend Workspace         │
│  Chat │ Ledger │ Timeline │ Why?    │
└───────────────┬─────────────────────┘
                │
                ▼
┌─────────────────────────────────────┐
│          FastAPI Backend            │
│         POST /chat                  │
└───────────────┬─────────────────────┘
                │
        ┌───────┴───────┐
        ▼               ▼
┌───────────────┐ ┌───────────────┐
│ Intent Router │ │  Enforcement  │
│ (cheap model) │ │    Engine     │
└───────┬───────┘ └───────┬───────┘
        │                 │
        └────────┬────────┘
                 ▼
        ┌───────────────┐
        │ Memory System │
        │ ├─ Retrieval  │
        │ ├─ Ingestion  │
        │ ├─ Dedup      │
        │ └─ Conflict   │
        └───────┬───────┘
                │
                ▼
        ┌───────────────┐
        │   SQLite DB   │
        │  (memories)   │
        └───────────────┘
```

---

## Project Structure

```
Antigravity-DecisionOS/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI routes
│   │   ├── engine/       # Reasoning, enforcement, intent
│   │   ├── llm/          # LLM provider abstraction
│   │   ├── memory/       # Ingestion, retrieval, conflicts
│   │   ├── models/       # SQLAlchemy models
│   │   ├── prompts/      # LLM prompts
│   │   ├── schemas/      # Pydantic schemas
│   │   ├── config.py     # Environment config
│   │   ├── database.py   # Database setup
│   │   └── main.py       # FastAPI app
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/
│   ├── index.html
│   ├── index.css         # Turing City aesthetic
│   └── app.js            # Frontend logic
│
└── README.md
```

---

## API Reference

### Projects

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/projects` | Create new project |
| GET | `/projects` | List all projects |
| GET | `/projects/{id}` | Get project details |

### Chat

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/projects/{id}/chat` | Chat with memory |
| POST | `/projects/{id}/ingest` | Ingest document |
| GET | `/projects/{id}/timeline` | Get events |

### Memory

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/projects/{id}/ledger` | Get all memories |
| GET | `/projects/{id}/memory/{mid}` | Get memory details |
| GET | `/projects/{id}/memory/{mid}/versions` | Get versions |
| POST | `/projects/{id}/memory/{mid}/resolve` | Resolve conflict |

---

## Design Philosophy

### Why Not Just "ChatGPT with Memory"?

| ChatGPT | DecisionOS |
|---------|------------|
| Memory is hidden | Memory is visible and governed |
| Remembers facts | Remembers **commitments**, **constraints**, **decisions** |
| No enforcement | **Actively enforces** past decisions |
| Can't explain why | **Every answer has receipts** |
| Stateless reasoning | **Continuity-aware** reasoning |

### Core Principles

1. **Conversation is disposable. Project memory is durable.**
2. **Memory is typed and governed.**
3. **Violations are challenged with citations.**
4. **Everything is versioned and auditable.**

---

## Technology Stack

- **Backend**: FastAPI, SQLAlchemy, SQLite
- **LLM**: OpenAI GPT-4o / Google Gemini 2.0 Flash
- **Frontend**: Vanilla JS, CSS3 (Glassmorphism)
- **Embeddings**: text-embedding-3-small / Gemini embedding

---
Tools Used: Gemini API, Token Company API, Devswarm, Google Antigravity IDE
---

## License

MIT License - Built for NexHacks 2026

---

<div align="center">

**DecisionOS** - *The future of project continuity*

Same Model. Same Prompt. **Only Memory Changed.**

</div>
