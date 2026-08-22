# ZettaBrain Platform

Unified AI platform combining **conversational AI** (RAG-powered Q&A) and **generative AI** (skill-based document generation) with multi-tenant team access control.

## Features

- **Chat** — Ask questions against team documents with hybrid retrieval (MMR + BM25 + FlashRank reranking)
- **Generate** — Produce documents using configurable skills with corpus grounding
- **Teams** — Multi-tenant system with role-based access (manager/member/viewer)
- **Verified** — Ed25519 cryptographic answer provenance signing
- **Multi-provider** — Ollama, OpenAI, Claude, Groq with per-team model delegation

## Quick Start

```bash
pip install -e .
zettabrain-platform setup
zettabrain-platform serve
```

Default admin: `admin` / `P@ssword!`

## API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /api/auth/token` | Login |
| `POST /api/chat/` | Conversational Q&A |
| `POST /api/generate/` | Document generation |
| `POST /api/ingest/{team_id}` | Ingest documents |
| `GET /api/generate/skills` | List available skills |
| `GET /api/generate/documents` | List generated documents |
| `GET /api/admin/settings` | System configuration |
| `GET /api/docs` | Interactive API docs |

## Architecture

```
zettabrain_platform/
├── auth.py              # JWT + bcrypt authentication
├── models.py            # SQLModel database schema
├── server.py            # FastAPI application
├── llm/                 # Unified LLM layer
│   ├── factory.py       # LangChain (chat) + direct providers (generation)
│   ├── model_resolver.py # Three-tier model resolution
│   └── providers/       # Ollama, Groq, Claude, OpenAI
├── retrieval/           # RAG engine
│   └── rag.py           # Hybrid retrieval + confidence scoring
├── generation/          # Document generation
│   ├── engine.py        # Skill execution engine
│   ├── skill_parser.py  # YAML frontmatter parser
│   └── models.py        # Skill, GenerationRequest/Result
├── ingestion/           # Document ingestion pipeline
│   └── pipeline.py      # Chunk + embed + store
└── routers/             # API endpoints
    ├── auth.py, teams.py, chat.py
    ├── generate.py      # Generation + streaming WebSocket
    ├── ingest.py, settings.py
```

## License

Proprietary — ZettaBrain
