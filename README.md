<div align="center">

# 🌐 Agent 3 — Website Intelligence Extraction Agent

### AI-Powered Website Crawling, Content Extraction & Structured Business Intelligence

[![Jira](https://img.shields.io/badge/Jira-Project%20Board-0052CC?style=for-the-badge&logo=jira)](https://ahed10ah.atlassian.net/jira/software/projects/A3WIE/boards/35?filter=&groupBy=none&atlOrigin=eyJpIjoiNTFiYTFjMTBiZGNjNGI2NmJhYTE0NjA3YWUzNGViM2YiLCJwIjoiaiJ9)

**📋 Project Management:**  
https://ahed10ah.atlassian.net/jira/software/projects/A3WIE/boards/35?filter=&groupBy=none&atlOrigin=eyJpIjoiNTFiYTFjMTBiZGNjNGI2NmJhYTE0NjA3YWUzNGViM2YiLCJwIjoiaiJ9

</div>

---

## 📖 About

This repository contains the implementation of **Agent 3**, an AI-powered system that crawls websites, extracts meaningful business information, and returns structured intelligence using modern AI techniques.

## 🚀 Project Board

All project planning, sprint management, and task tracking are managed in Jira.

➡️ **Jira Board:**  
https://ahed10ah.atlassian.net/jira/software/projects/A3WIE/boards/35?filter=&groupBy=none&atlOrigin=eyJpIjoiNTFiYTFjMTBiZGNjNGI2NmJhYTE0NjA3YWUzNGViM2YiLCJwIjoiaiJ9

---

## 🏗️ Architecture

The full system design lives in [`Agent3_Architecture.md`](./Agent3_Architecture.md).

Given a `companyId` + `websiteUrl`, the pipeline: normalizes the URL → fetches
the homepage → discovers internal links → fetches/classifies/extracts each page →
chunks the text → runs grounded AI structured extraction → persists the result →
exposes it via the API. Each module has one clear responsibility and passes typed
objects forward. Start with `agent3/orchestrator/scan_pipeline.py`.

## 📂 Repository structure

```
agent3/
├── api/                # Mission 13 — HTTP endpoints (routes) + request/response schemas
├── crawler/            # Missions 5-7 — url_normalizer, fetcher, link_discovery, shared models
├── classification/     # Mission 8 — page_classifier (PageType)
├── extraction/         # Missions 9-10 — text_extractor (ExtractedPage), chunker (Chunk)
├── ai/                 # Mission 11 — extractor, schemas, prompts/
│   ├── rag/            # RAG add-on — embedder, vector_store, retriever
│   └── tools/          # MCP add-on — tool_definitions, tool_handlers
├── orchestrator/       # scan_pipeline — runs all missions 5-12 in order
├── storage/            # Mission 12 — models (5 tables) + repository (all SQL)
├── common/             # config, logging (M16), errors (M15)
└── mcp_server/         # MCP add-on — Agent 3 exposed as tools for other agents

tests/                  # unit/ (per mission) · integration/ (full pipeline) · api/ (endpoints)
```

Each file starts with a header comment naming its mission and one-line job, and
currently contains only the imports that wire it to its connected modules — the
implementation is filled in per mission.

## 🛠️ Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```
