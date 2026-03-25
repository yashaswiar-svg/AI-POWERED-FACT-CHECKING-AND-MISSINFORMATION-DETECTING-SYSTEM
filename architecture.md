# Architecture

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Next.js Frontend                            │
│  ┌──────────────┐  ┌────────────────┐  ┌────────────────────────┐  │
│  │  Input Form  │  │  ClaimList.tsx │  │  StreamLog.tsx         │  │
│  │  (URL/text)  │  │  (claim cards) │  │  (pipeline progress)   │  │
│  └──────┬───────┘  └────────────────┘  └────────────────────────┘  │
└─────────┼───────────────────────────────────────────────────────────┘
          │ POST /extract
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        FastAPI Backend                              │
│                                                                     │
│  ┌─────────────┐    ┌──────────────────┐    ┌──────────────────┐   │
│  │  /health    │    │  /extract        │    │  /verify (stub)  │   │
│  │  (liveness) │    │  (main pipeline) │    │  (future)        │   │
│  └─────────────┘    └────────┬─────────┘    └──────────────────┘   │
│                              │                                      │
│              ┌───────────────┼────────────────────┐                 │
│              ▼               ▼                    ▼                 │
│       ┌────────────┐  ┌─────────────┐   ┌──────────────────┐       │
│       │  fetcher   │  │   claim_    │   │  search_client   │       │
│       │  .py       │  │  extractor  │   │  .py  (SerpAPI)  │       │
│       │            │  │  .py        │   │  [stub]          │       │
│       └──────┬─────┘  └──────┬──────┘   └────────┬─────────┘       │
│              │               │                   │                  │
│              ▼               ▼                   ▼                  │
│       ┌────────────┐  ┌─────────────┐   ┌──────────────────┐       │
│       │newspaper3k │  │  OpenAI     │   │  evidence_index  │       │
│       │readability │  │  GPT-4o     │   │  .py  (FAISS)    │       │
│       └────────────┘  │  (or mock)  │   │  [stub]          │       │
│                       └─────────────┘   └──────────────────┘       │
│                                                                     │
│       ┌──────────────────┐    ┌──────────────────────────────────┐  │
│       │  verifier.py     │    │  ai_detection.py (bonus, stub)   │  │
│       │  LLM + NLI agg.  │    │  LLM-generated text probability  │  │
│       │  [stub]          │    └──────────────────────────────────┘  │
│       └──────────────────┘                                          │
└─────────────────────────────────────────────────────────────────────┘
          │
          ▼
   External Services
   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
   │  OpenAI API  │  │  SerpAPI     │  │  Redis cache │
   └──────────────┘  └──────────────┘  └──────────────┘
```

---

## Data Flow

```
1.  User submits URL or raw text via the frontend form.
2.  Frontend sends POST /extract → FastAPI backend.
3.  If URL:
      fetcher.py downloads the page (httpx + newspaper3k / readability-lxml)
      and returns { title, author, date, text }.
4.  claim_extractor.py sends the article text to OpenAI GPT-4o with a
    structured few-shot prompt.  The LLM responds with a JSON array of
    atomic claims: [ {id, text, original_span: [start, end]} ].
    If OPENAI_API_KEY is absent → deterministic mock claims are returned.
5.  /extract returns { article, claims, meta } to the frontend.
6.  Frontend renders claim cards with a pipeline progress bar
    (Extracting ✓ → Searching … → Verifying …).

--- [Future steps, stubbed] ---

7.  For each claim, search_client.py generates a search query and calls
    SerpAPI to retrieve top-N URLs.
8.  fetcher.py retrieves each result URL and extracts text.
9.  evidence_index.py encodes passages with sentence-transformers and
    inserts them into a FAISS index.  ANN search returns the most relevant
    passages per claim.
10. verifier.py passes (claim, evidence passages) to the LLM + a local NLI
    model (e.g., cross-encoder/nli-deberta-v3-small) to produce a verdict:
    True / False / Partially True / Unverifiable, with a confidence score
    and citation list.
11. Aggregated accuracy report is returned and rendered in the UI.
```

---

## API Endpoints

### `GET /health`
Returns service liveness.
```json
{ "status": "ok", "version": "0.1.0" }
```

### `POST /extract`
Extracts atomic verifiable claims from article text or URL.

**Request body**
```json
{
  "url": "https://example.com/article",   // optional
  "text": "Raw article text …"            // optional; one of url/text required
}
```

**Response**
```json
{
  "article": {
    "title": "Article Title",
    "author": "Jane Doe",
    "date": "2024-01-15",
    "text": "Full article text …"
  },
  "claims": [
    {
      "id": "c1",
      "text": "The Eiffel Tower is 330 metres tall.",
      "original_span": [42, 80]
    }
  ],
  "meta": {
    "model_used": "gpt-4o (mock)",
    "runtime_ms": 142
  }
}
```

### `POST /verify` *(stub — future)*
Accepts extracted claims and returns verdicts with evidence.

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| LLM Provider | OpenAI GPT-4o | Best structured-output reliability; mock fallback for demos |
| Search Provider | SerpAPI | Stable Google results API; easy swap to Tavily/DDG |
| Vector Store | FAISS (local) | Zero-infra dependency for prototype; upgrade to Pinecone later |
| NLI Model | cross-encoder/nli-deberta-v3-small | Fast CPU inference, high accuracy for entailment |
| Frontend | Next.js + TypeScript | Production-grade; streaming-ready via Server-Sent Events |
| Backend | FastAPI | Async, auto-docs, Pydantic schema validation |
| Caching | Redis (optional) | Avoid re-fetching identical URLs; graceful degradation |
