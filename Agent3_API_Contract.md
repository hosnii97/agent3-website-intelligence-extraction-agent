# Agent 3 — Input / Output Contract (Mission 4)

## 1. Purpose

This document is the single source of truth for **how Agent 1 (and any
other consumer) calls Agent 3**. It defines the request shape, the
response shape on success, the response shape on failure, and the
validation rules that separate the two.

Missions 13 (API layer) and 15 (error handling) *implement* this
contract in code — this document is what they implement against, and
what the Agent 1 group should read instead of guessing field names from
the source.

Scope: this contract covers the primary entry point, **"scan a
website for a company."** It does not change based on transport —
the same fields apply whether Agent 1 calls Agent 3 over the REST API
(`POST /api/agents/agent3/scan-website`, see `Agent3_Architecture.md`
§7) or over the MCP tool (`scan_website`, see §12.1).

---

## 2. Call signature (quick reference)

```
scan_website(companyId, websiteUrl, domain?, options?) -> ScanResult | ErrorResponse
```

| Transport | How to call |
|---|---|
| REST | `POST /api/agents/agent3/scan-website` with the input JSON as the body |
| MCP tool | `scan_website({ companyId, websiteUrl, domain, options })` |

Both transports accept the same input shape (§3) and return the same
output shape (§4) or error shape (§5) — the contract is
transport-agnostic on purpose, so Agent 1 doesn't need two integrations.

---

## 3. Input contract

### 3.1 Required fields

| Field | Type | Rules | Notes |
|---|---|---|---|
| `companyId` | `string` | Non-empty. Must match an existing company known to Agent 1's system. | Echoed back unchanged on every response so Agent 1 can correlate. |
| `websiteUrl` | `string` | Must be an absolute URL with an `http://` or `https://` scheme. Max length 2048 chars. | This is what actually gets crawled. |

### 3.2 Optional fields

| Field | Type | Default | Rules | Notes |
|---|---|---|---|---|
| `domain` | `string` | Derived from `websiteUrl` | If provided, must match the host of `websiteUrl` (after normalization) or the request is rejected with `domain_mismatch`. | Convenience field for callers that already have it; never required. |
| `options.maxPages` | `integer` | `MAX_PAGES_PER_SCAN` (see `common/config.py`) | `1–50` | Caps how many internal pages get crawled beyond the homepage. |
| `options.forceRescan` | `boolean` | `false` | — | If `false` and a completed scan for this `companyId` already exists and is fresh (see `common/config.py` cache window), Agent 3 may return the cached `scanId`/result instead of re-crawling. |
| `options.callbackUrl` | `string` (URL) | `null` | Must be `https://` if provided | If set, Agent 3 POSTs the final `ScanResult` (§4) or `ErrorResponse` (§5) to this URL when the scan finishes, in addition to it being retrievable via the status endpoint. Enables async "fire and forget" instead of polling. |

Unknown fields in the input are ignored, not rejected — this keeps the
contract forward-compatible as new optional fields are added.

### 3.3 Example — minimal (required fields only)

```json
{
  "companyId": "company_123",
  "websiteUrl": "https://www.example.com"
}
```

### 3.4 Example — full

```json
{
  "companyId": "company_123",
  "websiteUrl": "https://www.example.com",
  "domain": "example.com",
  "options": {
    "maxPages": 20,
    "forceRescan": false,
    "callbackUrl": "https://agent1.internal/webhooks/agent3-scan-complete"
  }
}
```

---

## 4. Output contract — success

A scan always resolves to one of these `status` values:

| `status` | Meaning |
|---|---|
| `in_progress` | Scan accepted and running. Returned immediately by the initiating call; poll the status endpoint (or wait for `callbackUrl`) for the final result. |
| `completed` | Scan finished. `pagesScanned` pages were successfully processed. `pagesFailed` (individual pages that 404'd, timed out, etc.) does **not** move a scan out of `completed` — partial page failures are normal and expected on real websites. |
| `failed` | Scan-level failure — Agent 3 could not produce any usable result (e.g. homepage entirely unreachable, no pages could be crawled). See §5 for the shape returned in this case. |

### 4.1 Response fields

| Field | Type | Present when | Description |
|---|---|---|---|
| `companyId` | `string` | always | Echoed from the request. |
| `scanId` | `string` | always | Unique ID for this scan run. Use it to poll `GET /api/agents/agent3/scans/{scanId}`. |
| `status` | `"in_progress" \| "completed" \| "failed"` | always | See table above. |
| `pagesScanned` | `integer` | `status != in_progress` | Count of pages successfully fetched, classified, and extracted. |
| `pagesFailed` | `integer` | `status != in_progress` | Count of discovered pages that were attempted but failed (timeout, 404, blocked, etc.). |
| `extractedDataSummary` | `object` | `status == completed` | Cheap, boolean-only summary — see §4.2. Lets Agent 1 make quick decisions without fetching the full `WebsiteIntelligence` payload. |
| `startedAt` | `string` (ISO 8601) | always | When the scan began. |
| `completedAt` | `string` (ISO 8601) | `status != in_progress` | When the scan finished. |

### 4.2 `extractedDataSummary` fields

Each is a plain boolean: "did we find and confidently extract this
category of content." All are `false` (not omitted) when not found, so
Agent 1 can rely on the key always being present.

| Field | True means |
|---|---|
| `hasPricing` | A pricing page or pricing information was found and extracted. |
| `hasBlog` | A blog/content section was found. |
| `hasTerms` | A Terms of Service / Terms & Conditions page was found. |
| `hasPrivacyPolicy` | A Privacy Policy page was found. |
| `hasCaseStudies` | Case studies / customer stories were found. |

This is a **summary only**. The full structured extraction (the
`WebsiteIntelligence` object — company overview, products, pricing
detail, sources, etc., see `Agent3_Architecture.md` §4) is fetched
separately via `GET /api/companies/{companyId}/website-intelligence`.
Agent 3 keeps these separate so a caller that only needs "does this
company have a pricing page, yes/no" doesn't have to pull the entire
(larger, slower) intelligence payload.

### 4.3 Example — in progress (immediate response to the initiating call)

```json
{
  "companyId": "company_123",
  "scanId": "scan_456",
  "status": "in_progress",
  "startedAt": "2026-07-21T10:15:00Z"
}
```

### 4.4 Example — completed (final result, from status poll or callback)

```json
{
  "companyId": "company_123",
  "scanId": "scan_456",
  "status": "completed",
  "pagesScanned": 12,
  "pagesFailed": 1,
  "extractedDataSummary": {
    "hasPricing": true,
    "hasBlog": true,
    "hasTerms": true,
    "hasPrivacyPolicy": true,
    "hasCaseStudies": false
  },
  "startedAt": "2026-07-21T10:15:00Z",
  "completedAt": "2026-07-21T10:16:42Z"
}
```

---

## 5. Output contract — error response

Two different kinds of "error" exist, and Agent 3 tells them apart
clearly so Agent 1 never has to guess:

1. **Input rejected before a scan starts** (bad `companyId`, malformed
   `websiteUrl`, etc.) — returned synchronously, HTTP `400`.
2. **Scan-level failure** (the scan was accepted but couldn't complete
   at all — e.g. the site never responded) — `status: "failed"` on the
   scan resource, HTTP `200` when fetched via the status endpoint
   (the request to *check status* succeeded, even though the *scan*
   did not).

Both use the same JSON shape:

### 5.1 Error response fields

| Field | Type | Description |
|---|---|---|
| `companyId` | `string` | Echoed from the request, when available. |
| `scanId` | `string \| null` | `null` for input-validation errors (a scan was never created); set for scan-level failures. |
| `status` | `"error" \| "failed"` | `"error"` = input rejected, no scan created. `"failed"` = scan created but could not complete. |
| `errorType` | `string` (enum, §5.2) | Machine-readable reason. |
| `message` | `string` | Human-readable explanation, safe to log/display. |
| `retryable` | `boolean` | Whether Agent 1 should automatically retry later without changes. `false` means retrying with the same input will fail again — something about the input or the target site itself is the problem. |
| `details` | `object \| null` | Optional extra context (e.g. which field failed validation). |

### 5.2 `errorType` values and retry guidance

| `errorType` | `status` | `retryable` | Meaning |
|---|---|---|---|
| `invalid_input` | `error` | `false` | Missing/malformed required field(s). See `details.field`. |
| `invalid_url` | `error` | `false` | `websiteUrl` is not a valid absolute `http(s)` URL. |
| `domain_mismatch` | `error` | `false` | Provided `domain` doesn't match the host of `websiteUrl`. |
| `company_not_found` | `error` | `false` | `companyId` doesn't correspond to a known company. |
| `website_unreachable` | `failed` | `true` | Homepage could not be fetched within the timeout (DNS failure, connection refused, etc.). |
| `timeout` | `failed` | `true` | Scan exceeded its overall time budget. |
| `blocked` | `failed` | `false` | Site actively blocked the crawler (e.g. `robots.txt` disallow, WAF block, `403`). |
| `no_pages_found` | `failed` | `false` | Homepage fetched, but no crawlable internal pages were discoverable. |
| `ai_extraction_failed` | `failed` | `true` | Pages were crawled, but structured AI extraction failed validation after retries. |
| `internal_error` | `error` / `failed` | `true` | Unexpected Agent 3-side failure. Always safe to retry once. |

### 5.3 HTTP status code mapping (REST transport)

| Situation | HTTP status | Body |
|---|---|---|
| Input validation failed | `400 Bad Request` | Error response, `status: "error"` |
| `companyId` unknown | `404 Not Found` | Error response, `status: "error"`, `errorType: company_not_found` |
| Scan accepted | `202 Accepted` | Success response, `status: "in_progress"` |
| Status poll, scan still running | `200 OK` | Success response, `status: "in_progress"` |
| Status poll, scan completed | `200 OK` | Success response, `status: "completed"` |
| Status poll, scan failed | `200 OK` | Error response, `status: "failed"` (the *poll itself* succeeded) |
| Unexpected server-side failure | `500 Internal Server Error` | Error response, `errorType: internal_error` |

### 5.4 Examples

Invalid input (missing `websiteUrl`):

```json
{
  "companyId": "company_123",
  "scanId": null,
  "status": "error",
  "errorType": "invalid_input",
  "message": "websiteUrl is required.",
  "retryable": false,
  "details": { "field": "websiteUrl" }
}
```

Malformed URL:

```json
{
  "companyId": "company_123",
  "scanId": null,
  "status": "error",
  "errorType": "invalid_url",
  "message": "websiteUrl must be an absolute http(s) URL.",
  "retryable": false,
  "details": { "field": "websiteUrl", "value": "example.com" }
}
```

Scan-level failure (site unreachable):

```json
{
  "companyId": "company_123",
  "scanId": "scan_789",
  "status": "failed",
  "errorType": "website_unreachable",
  "message": "The website could not be reached within the configured timeout.",
  "retryable": true,
  "details": null
}
```

---

## 6. Validation rules Agent 3 enforces (so Agent 1 knows what's "invalid")

Checked in this order; the first failure wins and is returned
immediately (no partial/scan-level side effects on validation
failure):

1. `companyId` present, non-empty string.
2. `websiteUrl` present, parses as an absolute URL, scheme is `http`
   or `https`.
3. If `domain` is provided, it matches the normalized host of
   `websiteUrl`.
4. `companyId` corresponds to a known company (checked against
   Agent 1's company store).
5. If `options` is present: `maxPages` (if set) is an integer between
   1 and 50; `callbackUrl` (if set) is an `https://` URL.

Anything after step 4 (site unreachable, blocked, times out, no pages
found, AI extraction fails) is **not** an input-validation problem —
the input was fine, so a `scanId` is created and the failure is
reported as `status: "failed"` on that scan (§5.2), not as a `400`.

---

## 7. Compatibility notes

- New optional input fields may be added under `options` without
  breaking existing callers — always additive, never removing/renaming
  existing fields without a version bump.
- New boolean keys may be added to `extractedDataSummary` over time
  (e.g. `hasFaq`, `hasCareers`) — Agent 1 should read keys it cares
  about and ignore unknown ones rather than asserting an exact key set.
- New `errorType` values may be added; unrecognized ones should be
  treated by Agent 1 as `retryable: false` unless the `retryable` field
  says otherwise (the field is always authoritative — never infer
  retry behavior from `errorType` alone).

---

## 8. Cheat sheet for the Agent 1 group

- **Call:** `POST /api/agents/agent3/scan-website` with `{ companyId, websiteUrl }` (domain optional).
- **You get back immediately:** `{ companyId, scanId, status: "in_progress" }`.
- **Poll:** `GET /api/agents/agent3/scans/{scanId}` until `status` is `"completed"` or `"failed"` (or set `options.callbackUrl` instead of polling).
- **On `"completed"`:** read `pagesScanned`, `pagesFailed`, `extractedDataSummary` directly off this response; fetch `GET /api/companies/{companyId}/website-intelligence` only if you need the full structured data.
- **On `"failed"` or `"error"`:** check `retryable` before deciding whether to retry — don't retry blindly, and don't retry `retryable: false` responses without changing the input.
