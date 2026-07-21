# Agent 3 — Website Intelligence Extraction Agent
## System Architecture

---

## 1. Purpose (one sentence)

Given a `companyId` + `websiteUrl`, safely scan the company's website,
extract clean text, classify pages, run AI structured extraction with
source grounding, and store the result so Agent 1 (and future consumers)
can retrieve structured "website intelligence" by company ID.

---

## 2. High-level flow

```
companyId + websiteUrl
        │
        ▼
 [1] URL Normalizer         → clean, validated URL + domain
        │
        ▼
 [2] Homepage Fetcher        → HTML + fetch status
        │
        ▼
 [3] Link Discovery          → list of candidate internal URLs
        │
        ▼
 [4] Page Fetcher (loop)     → HTML per page (reuses fetcher from step 2)
        │
        ▼
 [5] Page Classifier         → page_type per URL
        │
        ▼
 [6] Content Extractor       → clean_text, title, headings per page
        │
        ▼
 [7] Chunker                 → chunks + metadata
        │
        ▼
 [8] AI Structured Extractor → structured JSON (grounded, sourced)
        │
        ▼
 [9] Persistence Layer       → scan, pages, chunks, intelligence saved
        │
        ▼
 [10] API Layer              → exposes scan + retrieval endpoints
```

Each numbered box = one Python module with one clear responsibility.
No module should know about the internals of another — they only pass
typed objects (dataclasses / pydantic models) forward.

---

## 3. Repository structure (full file list)

Every file below has a one-line job. If a junior dev opens any file and
reads the top comment, they should immediately know: which mission it
belongs to, and what it's responsible for. Nothing more.

```
agent3/
│
├── api/
│   ├── __init__.py
│   ├── routes.py                     # Mission 13 — defines the 3 endpoints (scan, status, get-intelligence)
│   └── schemas.py                    # Mission 13 — request/response shapes for the API (pydantic)
│
├── crawler/
│   ├── __init__.py
│   ├── url_normalizer.py             # Mission 5  — cleans/validates the input URL before anything else runs
│   ├── fetcher.py                    # Mission 6  — safely downloads a page (homepage or any internal page)
│   ├── link_discovery.py             # Mission 7  — finds and filters internal links worth scanning
│   └── models.py                     # Shared    — FetchResult / FetchStatus used by fetcher.py and everyone downstream
│
├── classification/
│   ├── __init__.py
│   └── page_classifier.py            # Mission 8  — decides what TYPE each page is (pricing, blog, legal, etc.)
│
├── extraction/
│   ├── __init__.py
│   ├── text_extractor.py             # Mission 9  — turns raw HTML into clean readable text + title + headings
│   └── chunker.py                    # Mission 10 — splits clean text into small chunks with metadata
│
├── ai/
│   ├── __init__.py
│   ├── prompts/
│   │   ├── __init__.py
│   │   └── website_intelligence_prompt.py   # Mission 11 — the actual prompt text sent to the LLM
│   ├── extractor.py                  # Mission 11 — calls the LLM, validates its JSON output against schemas.py
│   ├── schemas.py                    # Mission 11 — the exact JSON shape the AI must return (pydantic)
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── embedder.py               # RAG add-on — turns chunk text into a vector
│   │   ├── vector_store.py           # RAG add-on — stores/searches vectors (FAISS or pgvector)
│   │   └── retriever.py              # RAG add-on — given a question, returns the top-k most relevant chunks
│   └── tools/
│       ├── __init__.py
│       ├── tool_definitions.py       # MCP add-on — describes the callable tools (search_chunks, etc.)
│       └── tool_handlers.py          # MCP add-on — the real functions those tools run under the hood
│
├── orchestrator/
│   ├── __init__.py
│   └── scan_pipeline.py              # Runs ALL missions 5–12 in order. Read this file first if you're new.
│
├── storage/
│   ├── __init__.py
│   ├── models.py                     # Mission 12 — the 5 database tables (scans, pages, chunks, intelligence, errors)
│   └── repository.py                 # Mission 12 — save()/get() functions; the ONLY place that writes SQL
│
├── common/
│   ├── __init__.py
│   ├── config.py                     # All settings in one place: timeouts, limits, user-agent, LLM model name
│   ├── logging.py                    # Mission 16 — one shared logger every module uses (scan_id, url, etc.)
│   └── errors.py                     # Mission 15 — shared error types + the standard error JSON shape
│
├── mcp_server/
│   └── agent3_server.py              # MCP add-on — exposes Agent 3 as a tool other agents can call
│
└── tests/
    ├── unit/
    │   ├── test_url_normalizer.py    # Mission 5
    │   ├── test_fetcher.py           # Mission 6
    │   ├── test_link_discovery.py    # Mission 7
    │   ├── test_page_classifier.py   # Mission 8
    │   ├── test_text_extractor.py    # Mission 9
    │   ├── test_chunker.py           # Mission 10
    │   └── test_ai_extractor.py      # Mission 11
    ├── integration/
    │   └── test_full_scan_pipeline.py   # runs the whole pipeline against a mock website
    └── api/
        └── test_routes.py            # Mission 13 — hits the actual endpoints
```



### 3.1 File-by-file guide (for onboarding juniors)

Give each junior this table filtered to *their* row(s) — they should
never need to open a file outside their own folder to understand what
they're supposed to build.

| File | Mission | In plain words |
|---|---|---|
| `crawler/url_normalizer.py` | 5 | "Fix messy URLs before we use them" |
| `crawler/fetcher.py` | 6 | "Download a page without crashing, ever" |
| `crawler/link_discovery.py` | 7 | "Find the pages worth reading on this site" |
| `classification/page_classifier.py` | 8 | "Guess what kind of page this is" |
| `extraction/text_extractor.py` | 9 | "Strip the HTML junk, keep the real text" |
| `extraction/chunker.py` | 10 | "Cut long text into small labeled pieces" |
| `ai/rag/embedder.py` | RAG | "Turn a chunk of text into a searchable vector" |
| `ai/rag/vector_store.py` | RAG | "Where the vectors live, and how we search them" |
| `ai/rag/retriever.py` | RAG | "Given a topic, fetch the most relevant chunks" |
| `ai/prompts/website_intelligence_prompt.py` | 11 | "The exact instructions we give the AI" |
| `ai/extractor.py` | 11 | "Send the prompt, get JSON back, check it's valid" |
| `ai/tools/*` | MCP | "Let the AI ask for what it needs instead of us deciding for it" |
| `storage/models.py` | 12 | "The shape of our database tables" |
| `storage/repository.py` | 12 | "Every save/read of the database goes through here" |
| `api/routes.py` | 13 | "The 3 doors other agents knock on" |
| `orchestrator/scan_pipeline.py` | — | "The recipe that runs every step in order" |
| `common/errors.py` | 15 | "One shared way to describe what went wrong" |
| `common/logging.py` | 16 | "One shared way to write logs" |

**Rule of thumb for juniors:** if you're not sure where new code
belongs, ask "which mission number is this?" — that number tells you
the folder.

---

## 4. Core data contracts (define these before writing pipeline code)

These are the "interfaces" between missions — get the team to agree on
these in one sitting (this *is* Mission 3/4's deliverable).

```python
# crawler/models.py
class FetchStatus(str, Enum):
    SUCCESS = "success"
    REDIRECTED = "redirected"
    TIMEOUT = "timeout"
    BLOCKED = "blocked"
    NOT_FOUND = "not_found"
    SERVER_ERROR = "server_error"
    FAILED = "failed"

@dataclass
class FetchResult:
    url: str
    final_url: str
    status: FetchStatus
    http_status_code: Optional[int]
    html: Optional[str]
    elapsed_ms: int
    error_reason: Optional[str]

# classification/page_classifier.py
class PageType(str, Enum):
    HOMEPAGE = "homepage"
    ABOUT = "about"
    PRODUCT = "product"
    SERVICE = "service"
    PRICING = "pricing"
    BLOG = "blog"
    CASE_STUDY = "case_study"
    CUSTOMER = "customer"
    FAQ = "faq"
    CONTACT = "contact"
    TERMS = "terms"
    PRIVACY_POLICY = "privacy_policy"
    COOKIE_POLICY = "cookie_policy"
    REFUND_POLICY = "refund_policy"
    LEGAL = "legal"
    CAREER = "career"
    GENERAL = "general"
    UNKNOWN = "unknown"

# extraction/text_extractor.py
@dataclass
class ExtractedPage:
    url: str
    page_type: PageType
    title: Optional[str]
    meta_description: Optional[str]
    headings: list[str]
    clean_text: str
    raw_text_length: int
    language: Optional[str]
    fetch_status: FetchStatus

# extraction/chunker.py
@dataclass
class Chunk:
    company_id: str
    page_url: str
    page_type: PageType
    chunk_index: int
    title: Optional[str]
    text: str

# ai/schemas.py  (pydantic — this is what the LLM must return, validated)
class SourcedField(BaseModel):
    value: str
    confidence: Literal["high", "medium", "low"]
    sources: list[HttpUrl]

class WebsiteIntelligence(BaseModel):
    company_overview: SourcedField
    products_and_services: SourcedField
    pricing: Optional[SourcedField]
    target_customers: Optional[SourcedField]
    case_studies: Optional[SourcedField]
    contact_details: Optional[SourcedField]
    legal_pages: dict          # termsAvailable, privacyPolicyAvailable, etc.
    missing_information: list[str]
```

---

## 5. Orchestrator (the pipeline owner)

One function owns the scan lifecycle, catches per-page errors so one bad
page never kills the whole scan, and always produces a final status.

```python
# orchestrator/scan_pipeline.py
def run_website_scan(company_id: str, website_url: str) -> ScanResult:
    scan_id = generate_scan_id()
    log.info("scan_started", scan_id=scan_id, company_id=company_id)

    url = normalize_url(website_url)                     # Mission 5
    homepage = fetch_homepage(url)                        # Mission 6
    if homepage.status not in (FetchStatus.SUCCESS, FetchStatus.REDIRECTED):
        return _fail_scan(scan_id, company_id, homepage)

    candidate_urls = discover_links(homepage)              # Mission 7
    pages: list[ExtractedPage] = []

    for page_url in candidate_urls[:MAX_PAGES]:
        fetch_result = fetch_page(page_url)                # reuses fetcher
        if fetch_result.status != FetchStatus.SUCCESS:
            log.warning("page_scan_failed", scan_id=scan_id, url=page_url,
                        reason=fetch_result.error_reason)
            continue                                        # don't fail the whole scan
        page_type = classify_page(page_url, fetch_result.html)  # Mission 8
        extracted = extract_text(fetch_result, page_type)        # Mission 9
        pages.append(extracted)

    chunks = chunk_pages(pages, company_id)                 # Mission 10
    intelligence = extract_structured_intelligence(chunks)   # Mission 11

    save_scan_results(scan_id, company_id, homepage, pages, chunks, intelligence)  # Mission 12
    log.info("scan_completed", scan_id=scan_id, pages_scanned=len(pages))

    return ScanResult(scan_id=scan_id, status="completed",
                       pages_scanned=len(pages),
                       pages_failed=len(candidate_urls) - len(pages))
```

This function is the one place a new developer should read first —
it reads almost like the mission list itself.

---

## 6. Database schema (Mission 12)

```
website_scans
├── scan_id (PK)
├── company_id
├── website_url
├── domain
├── status              (in_progress | completed | failed)
├── pages_discovered
├── pages_scanned
├── pages_failed
├── started_at
├── completed_at
└── error_summary

scanned_pages
├── page_id (PK)
├── scan_id (FK)
├── company_id
├── page_url
├── page_type
├── page_title
├── http_status
├── clean_text
├── metadata (JSON)
└── created_at

content_chunks
├── chunk_id (PK)
├── page_id (FK)
├── company_id
├── chunk_index
├── text
└── metadata (JSON)

website_intelligence
├── intelligence_id (PK)
├── company_id
├── scan_id (FK)
├── data (JSON — the validated WebsiteIntelligence object)
└── created_at

scan_errors
├── error_id (PK)
├── scan_id (FK)
├── page_url (nullable — null if scan-level error)
├── error_type
├── message
└── created_at
```

---

## 7. API layer (Mission 13)

```
POST /api/agents/agent3/scan-website
  body: { companyId, websiteUrl }
  → 202 { scanId, status: "in_progress" }

GET /api/agents/agent3/scans/{scanId}
  → { scanId, status, pagesScanned, pagesFailed, ... }

GET /api/companies/{companyId}/website-intelligence
  → the WebsiteIntelligence object (latest completed scan)
```

Keep the API layer thin — it should only validate input, call the
orchestrator, and shape the response. All logic lives in `orchestrator/`
and below, so it's testable without spinning up a web server.

---

## 8. Error handling strategy (Mission 15)

- **Page-level errors** (one page 404s) → logged, skipped, scan continues.
- **Scan-level errors** (homepage unreachable) → scan marked `failed`,
  reason stored, returned via the shared error schema:

```json
{
  "status": "failed",
  "errorType": "website_unreachable",
  "message": "The website could not be reached within the configured timeout.",
  "retryable": true
}
```

- Every error type maps to `retryable: true/false` so Agent 1 knows
  whether to automatically retry later (timeouts, 5xx → retryable;
  invalid URL, 404 → not retryable).

---

## 9. Config (single source of truth)

```python
# common/config.py
REQUEST_TIMEOUT_SECONDS = 15
MAX_PAGES_PER_SCAN = 15
MAX_CRAWL_DEPTH = 2
MAX_CONTENT_SIZE_BYTES = 5_000_000
CHUNK_SIZE_TOKENS = 600
CHUNK_OVERLAP_TOKENS = 80
USER_AGENT = "Agent3-WebsiteIntelligenceBot/1.0"
LLM_MODEL = "claude-sonnet-4-6"
LLM_TEMPERATURE = 0.0   # deterministic structured extraction
```

---

## 10. AI extraction design ( Mission 11)

- Input: relevant chunks (filter by `page_type` — pricing questions only
  need pricing/homepage chunks, not blog posts).
- Prompt requires the model to output **only JSON**, matching the
  `WebsiteIntelligence` pydantic schema.
- Every field must cite `sources` (URLs) — if the model can't point to a
  source, the field must be `null`/`not_available`, not a guess.
- Validate output with pydantic; on validation failure, log
  `ai_output_parsing_failed` and retry once with a stricter reminder
  appended to the prompt before giving up.
- Temperature 0.0, no creative sampling — this is extraction, not writing.

---

## 11. RAG & Retrieval Layer

Mission 10 (chunking) is only half of RAG — the other half is
**retrieval**: turning chunks into something searchable, so extraction
pulls in only the chunks relevant to each field instead of dumping every
chunk into the prompt.

```
scanned pages
     │
     ▼
 [Chunker]  ──►  chunks (text + metadata)
     │
     ▼
 [Embedder]  ──►  vector per chunk (e.g. text-embedding-3-small, or
     │              a local sentence-transformers model)
     ▼
 [Vector Store]  ──►  stores (vector, chunk_id, company_id, page_type)
     │
     ▼
 [Retriever]  ──►  given a query ("pricing information"), returns
                     top-k most similar chunks for that company only
```

**Module addition:**

```
ai/
├── rag/
│   ├── embedder.py        # text → vector
│   ├── vector_store.py     # add/query (pgvector, Chroma, FAISS, etc.)
│   └── retriever.py        # top-k similarity search, filtered by company_id
```

**How it plugs into extraction (Mission 11):**

Instead of "send all chunks for this company to the LLM," the flow becomes:

```python
def build_context_for_field(company_id: str, field_query: str, k: int = 5) -> list[Chunk]:
    query_vector = embed(field_query)
    return vector_store.search(query_vector, filter={"company_id": company_id}, top_k=k)
```

So extracting `pricing` retrieves the k chunks most semantically similar
to "pricing information," rather than relying on `page_type == pricing`
alone — this catches pricing mentioned on a FAQ or homepage too, and keeps
the context sent to the LLM small and relevant (cheaper, more accurate,
less chance of the model drifting off-topic).

**Practical scope note:** for a student-project-sized site (10-20 pages,
maybe 50-150 chunks), a simple in-memory vector index (FAISS or even
cosine similarity over a numpy array) is genuinely enough — you don't
need a hosted vector DB to demonstrate this cleanly. Save the vectors
alongside the chunk in Postgres (`pgvector` extension) if you want it
persisted without adding a new piece of infrastructure.

**Acceptance criteria to add:**
- Chunks are embedded and stored with a retrievable vector.
- Retrieval returns chunks scoped to the correct `company_id` only
  (never leak one company's data into another's extraction).
- Retrieval quality is spot-checked (does querying "refund policy"
  actually surface the refund page chunk?).

---

## 12. MCP / Tool-Calling Layer

Model Context Protocol (MCP) is a standard way to expose functionality as
**tools an LLM can call**, rather than hardcoding a fixed script sequence.
There are two places this fits naturally in Agent 3:

### 12.1 Agent 3 exposed as an MCP tool (for Agent 1 / other agents)

Instead of Agent 1 only calling Agent 3's REST API directly, you can wrap
the same functionality as an MCP server so any MCP-compatible agent can
call it as a tool:

```
mcp_server/
└── agent3_server.py
    tools:
      - scan_website(companyId, websiteUrl) -> scanId
      - get_scan_status(scanId) -> status
      - get_website_intelligence(companyId) -> WebsiteIntelligence
```

This is the same three endpoints from Mission 13, just described with an
MCP tool schema instead of (or in addition to) an OpenAPI/REST schema.
Useful if your course wants to demonstrate real agent-to-agent tool
calling rather than plain HTTP integration.

### 12.2 Internal tool-calling during extraction (agentic retrieval)

Instead of a fixed pipeline that always does "chunk → embed → retrieve top-k
→ extract," you can make Mission 11 itself agentic: give the LLM tools and
let it decide what it needs.

```
Tools exposed to the extraction LLM:
  - search_chunks(query: str, top_k: int) -> list[Chunk]
  - get_page_by_type(page_type: str) -> ExtractedPage
  - get_page_by_url(url: str) -> ExtractedPage
```

Flow: the model is given the extraction task ("build the WebsiteIntelligence
object") and calls `search_chunks("pricing plans")`, `search_chunks("refund
policy")`, etc. on its own, gathering only what it needs per field, before
producing the final structured JSON.

**Tradeoff to discuss with your team before building this:**
- **Fixed pipeline (simpler, what's in Section 10):** predictable, cheap,
  easy to test, one LLM call per scan (or per field).
- **Agentic/MCP tool-calling (more advanced, matches course's "tool
  calling" + "agentic flow" concepts more directly):** more flexible and
  a better demo of agentic design, but more LLM calls (cost/latency), and
  needs careful limits (max tool calls per scan) so it can't loop forever.

Given the project timeline, a reasonable plan: **build the fixed
RAG pipeline first (Section 11) to get a working end-to-end demo**, then
if time allows, layer the MCP tool-calling version on top as the "advanced"
version for the final demo — it reuses the same `retriever.py` and
`vector_store.py` underneath either way.

**Module addition:**

```
ai/
├── tools/
│   ├── tool_definitions.py   # MCP-style schema for search_chunks, get_page_by_type, etc.
│   └── tool_handlers.py       # actual functions the tools call under the hood
```

---

## 13. Why this architecture is "clean"

- **Single responsibility per module** — matches missions 1:1, so any
  teammate can work on their piece without reading the others' code.
- **Typed contracts between steps** — nobody has to guess what shape of
  data they're receiving.
- **Failures are data, not exceptions** — `FetchStatus`, error schemas,
  and per-page try/except mean one bad page or one AI hiccup never
  crashes the whole scan.
- **The orchestrator is the only place that knows the full flow** —
  great for onboarding and for the Mission 20 demo walkthrough.
- **Testable in isolation** — every module takes typed input and
  returns typed output, so unit tests don't need a live website or a
  running API server.
- **RAG and MCP are additive, not required for the first working
  version** — get the fixed pipeline (Sections 1-10) working end-to-end
  first, then layer retrieval and tool-calling on top once the basics
  are solid.
