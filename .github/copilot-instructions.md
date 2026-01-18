# DecisionOS - AI Coding Agent Instructions

## Project Overview

**DecisionOS** is a Project Continuity Copilot that solves LLM statelessness by introducing a persistent cognitive layer for long-running projects. Unlike stateless LLMs, DecisionOS remembers decisions, enforces commitments, and detects contradictions.

**Core Thesis**: "Same model. Same prompt. Only memory changed."

---

## Architecture Overview

### Three Core Layers

1. **Memory System** (`backend/app/memory/`)
   - Typed atoms: Decision, Commitment, Constraint, Goal, Failure, Assumption, Belief, Preference, Exception
   - Two-stage retrieval: Vector similarity (Stage A) → Ranking (Stage B) with scoring function
   - Versioning, deduplication, conflict detection
   - **Key insight**: Memory types have priority scores (Commitment/Constraint = 1.0, Preference = 0.5)

2. **Enforcement Engine** (`backend/app/engine/enforcement.py`)
   - Runs before every response to check for violations against commitments/constraints
   - Challenges user with citations if violation detected
   - **Critical pattern**: Returns `ViolationCheckResult` with severity + suggested response

3. **Reasoning Engine** (`backend/app/engine/reasoning.py`)
   - Orchestrates: Intent Classification → Memory Retrieval → Enforcement Check → Response Generation
   - Attaches debug metadata with citations
   - Publishes events for observability

---

## Data Flow (Single Chat Turn)

```
User Message → Intent Router (cheap model) 
  → Retrieval Pipeline (vector + keyword search)
  → Enforcement Engine (violation check)
  → Reasoning Engine (heavy/mid model based on intent)
  → Ingestion Pipeline (extract new memories)
  → Response + Debug Metadata + Events
```

**File**: [backend/app/api/chat.py](backend/app/api/chat.py#L30-L80) shows this orchestration clearly.

---

## Key Developer Patterns

### 1. Model Tiering System
- **CHEAP**: Intent routing, extraction, deduplication (gpt-4o-mini / gemini-2.5-flash)
- **MID**: Standard responses, planning
- **HEAVY**: Enforcement, deep synthesis (gpt-4o / gemini-2.5-pro)

Access via `get_model_for_task()` or `get_model_for_tier()` from [backend/app/llm/router.py](backend/app/llm/router.py).

### 2. Async SQLAlchemy with SQLite
- Uses `async_sessionmaker` dependency injection via `Depends(get_db)`
- Foreign key constraints enabled via PRAGMA for SQLite
- Supports migration to PostgreSQL for production
- **Reference**: [backend/app/database.py](backend/app/database.py)

### 3. Intent-Driven Response Selection
- 11 intent types defined in `IntentRouter` (Question, Decision, Commitment, Conflict, etc.)
- Intent classification determines: model tier, whether enforcement needed, whether memory needed
- **See**: [backend/app/engine/intent_router.py](backend/app/engine/intent_router.py#L28-L60)

### 4. Event Publishing for Observability
- Every reasoning step publishes events (SSE stream to frontend)
- Turn ID groups events together across the pipeline
- Frontend shows real-time pipeline notifications
- **Configuration**: Follow-through mode (`settings.follow_through`) enables structured logging

### 5. Memory Scoring Function
```
score = 0.40 * semantic_similarity +
        0.20 * importance +
        0.20 * recency_weight +
        0.10 * confidence +
        0.10 * type_boost
```
Type boosts prioritize commitments/constraints. **Reference**: [backend/app/memory/retrieval.py](backend/app/memory/retrieval.py#L20-L45)

---

## Critical Integration Points

### LLM Provider Setup
- **File**: [backend/app/config.py](backend/app/config.py)
- Environment variables: `LLM_PROVIDER` (openai|gemini), provider-specific API keys
- Singleton pattern via `get_llm_provider()` - reuses connection across requests
- Embedding model obtained from same provider

### Database Models
- Base class: `Base` from `database.py`
- Core models: `MemoryAtom`, `MemoryVersion`, `EvidenceChunk`, `Project`, `OpsLog`
- All inherit SQLAlchemy ORM mappings with UUID primary keys

### Frontend-Backend Communication
- Chat endpoint accepts `ChatRequest` (message, mode) → returns `ChatResponse` (text, debug metadata, citations)
- Two chat modes: "Project Chat" (stateless, ingests every message) vs "Work Chat" (session-based)
- SSE stream for real-time event notifications
- **Frontend**: [frontend/app.js](frontend/app.js#L1-L80) handles both modes

---

## Conventions to Follow

### When Adding Memory Types
1. Add to `MemoryType` enum in [backend/app/models/memory.py](backend/app/models/memory.py)
2. Set TYPE_BOOST score in `RetrievalPipeline.TYPE_BOOSTS`
3. Update `IntentRouter.TIER_MAP` if it affects response selection
4. Add prompt context in [backend/app/prompts/extractor.py](backend/app/prompts/extractor.py)

### When Adding LLM Calls
1. Use `get_model_for_task(task_name)` or explicit tier: `get_model_for_tier(ModelTier.HEAVY)`
2. Include system prompt from `prompts/` module
3. For structured output, use Pydantic models for parsing
4. Emit trace events if part of reasoning pipeline: `trace_step()`, `trace_call()`, `trace_result()`

### Error Handling in Async Context
- Use try/except in async functions that call LLM
- Log with `logger.warning()` or `logger.error()` - don't raise unnecessarily
- Return empty/None gracefully (embeddings, retrieval, etc.)

---

## Testing & Debugging

### Environment Variables for Development
```
DEBUG=true           # Verbose logging
FOLLOW_THROUGH=true  # Structured tracing output
LLM_PROVIDER=gemini  # or 'openai'
GEMINI_API_KEY=...   # Required
```

### Key Entry Points for Debugging
- Chat flow: [backend/app/api/chat.py](backend/app/api/chat.py)
- Memory logic: [backend/app/memory/retrieval.py](backend/app/memory/retrieval.py)
- Enforcement violations: [backend/app/engine/enforcement.py](backend/app/engine/enforcement.py#L40-L80)
- Event publishing: [backend/app/events.py](backend/app/events.py)

---

## Common Tasks

### Adding a New API Endpoint
1. Create handler in appropriate module under `backend/app/api/`
2. Include `db: AsyncSession = Depends(get_db)` dependency
3. Return Pydantic schema from `backend/app/schemas/`
4. Register router in [backend/app/main.py](backend/app/main.py)

### Modifying Memory Retrieval
- Edit scoring weights in `RetrievalPipeline._score_candidate()`
- Adjust recency half-life if temporal decay changes
- Test with various memory types to ensure correct prioritization

### Adding LLM Provider
- Inherit from `LLMProvider` base class in [backend/app/llm/base.py](backend/app/llm/base.py)
- Implement: `complete_text()`, `embed_text()`, abstract methods
- Update config: add provider selection and model names
- Register in `get_llm_provider()` factory

---

## Project Structure Quick Reference

| Directory | Purpose |
|-----------|---------|
| `backend/app/api/` | HTTP endpoints (chat, memory, projects, work) |
| `backend/app/engine/` | Core reasoning: intent routing, enforcement, reasoning |
| `backend/app/memory/` | Retrieval, ingestion, deduplication, conflict detection |
| `backend/app/llm/` | Provider abstraction (OpenAI, Gemini) + router |
| `backend/app/models/` | SQLAlchemy ORM models |
| `backend/app/schemas/` | Pydantic request/response schemas |
| `backend/app/prompts/` | System prompts for LLM calls |
| `frontend/` | Vanilla JS + CSS (no framework) |
