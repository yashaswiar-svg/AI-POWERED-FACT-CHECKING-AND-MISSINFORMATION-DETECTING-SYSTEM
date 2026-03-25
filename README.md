# 🔍 Fact & Claim Verification System

An AI-powered fact-checking engine that validates text integrity against real-time web data. Paste a news article URL or raw text, and the system automatically extracts verifiable claims, searches for corroborating or contradicting evidence, and produces a detailed accuracy report with citations and confidence scores.

---

## ✨ Features

- **Claim Extraction** — Decomposes complex articles into discrete, atomic, verifiable statements using an LLM with structured JSON output
- **Evidence Retrieval** *(coming soon)* — Autonomously formulates search queries and cross-references real-world sources
- **Verification & Reporting** *(coming soon)* — Classifies each claim as True / False / Partially True / Unverifiable with citations and confidence scores
- **AI-Content Detection** *(bonus, coming soon)* — Estimates likelihood that the input was LLM-generated
- **Mock mode** — Runs fully without any API key for demo and testing purposes

---

## 🏗️ Architecture Summary

```
User Input (URL or Text)
        │
        ▼
   [Fetcher]  ←── newspaper3k / readability-lxml
        │
        ▼
[Claim Extractor] ←── OpenAI GPT-4o (or mock)
        │
        ▼
[Search Client]   ←── SerpAPI (stub)
        │
        ▼
[Evidence Index]  ←── FAISS vector store (stub)
        │
        ▼
   [Verifier]     ←── LLM + NLI aggregation (stub)
        │
        ▼
  Accuracy Report (JSON → Next.js UI)
```

See [`architecture.md`](./architecture.md) for full component diagram and API reference.

---

## 🚀 Quickstart

### Prerequisites
- Python 3.11+
- Node.js 18+
- (Optional) OpenAI API key

### 1. Clone & configure

```bash
git clone https://github.com/ACCHU04/fact-claim-verifier.git
cd fact-claim-verifier
cp .env.example .env
# Edit .env and add your API keys (leave blank to run in mock mode)
```

### 2. Run the backend

```bash
pip install -r requirements.txt
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

Health check: `http://localhost:8000/health`

### 3. Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Open: `http://localhost:3000`

### 4. Run with Docker Compose (recommended)

```bash
# 1. Create your .env first (required — even if empty)
cp .env.example .env

# 2. Build and start both services
docker compose up --build

# Backend  → http://localhost:8000
# Frontend → http://localhost:3000
```

Or build images individually (run from repo root):

```bash
cp .env.example .env
docker build -f infra/docker/backend.Dockerfile  -t fcv-backend  .
docker build -f infra/docker/frontend.Dockerfile -t fcv-frontend .
docker run -p 8000:8000 --env-file .env fcv-backend
docker run -p 3000:3000 -e NEXT_PUBLIC_API_URL=http://localhost:8000 fcv-frontend
```

### 5. Run tests

```bash
cd backend
pytest app/tests/ -v
```

---

## 🎯 Demo Scenarios

| Demo | URL / Text | Expected Outcome |
|------|-----------|-----------------|
| `demo1_true.json` | `https://example.com/article-true` | Claims verified as **True** against web sources |
| `demo2_false.json` | `https://example.com/article-false` | Claims flagged as **False** with contradicting evidence |
| `demo3_conflicting.json` | `https://example.com/article-conflict` | **Conflicting** evidence — demonstrates ambiguity handling |

> `demo3_conflicting.json` is the key scenario showcasing the system's ability to surface contradictory sources rather than forcing a binary verdict.

---

## 📁 Project Structure

```
fact-claim-verifier/
├── backend/          FastAPI app, claim extractor, verifier, search client
├── frontend/         Next.js UI with pipeline progress + claim cards
├── docs/             Prompt guides, evaluation plan, demo scenarios
├── examples/         Demo input/output JSON files
├── evaluation/       FEVER / LIAR dataset scripts and metrics
├── infra/            Dockerfiles
└── scripts/          Local run helpers
```

---

## 🔑 Environment Variables

See [`.env.example`](.env.example) for the full list. Key variables:

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | OpenAI API access (leave blank for mock mode) |
| `SERPAPI_KEY` | SerpAPI web search (leave blank to disable search) |
| `REDIS_URL` | Optional caching layer |
| `FAISS_INDEX_PATH` | Path to persist the FAISS vector index |

---

## 📜 License

MIT — see [LICENSE](./LICENSE)
