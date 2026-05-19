<div align="center">
  <h1>J.A.R.V.I.S</h1>
  <p><strong>Just A Rather Very Intelligent System</strong></p>
  <p><em>AI-Powered OSINT, Profile Analysis & Intelligent Assistant Platform</em></p>

  <div>
    <img src="https://img.shields.io/badge/Python-3.11+-blue?style=for-the-badge&logo=python" alt="Python" />
    <img src="https://img.shields.io/badge/FastAPI-0.109+-009688?style=for-the-badge&logo=fastapi" alt="FastAPI" />
    <img src="https://img.shields.io/badge/Next.js-15-black?style=for-the-badge&logo=next.js" alt="Next.js" />
    <img src="https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white" alt="TypeScript" />
  </div>
  <div style="margin-top: 5px;">
    <img src="https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white" alt="SQLite" />
    <img src="https://img.shields.io/badge/Ollama-Local_LLM-FF6347?style=for-the-badge&logo=ollama&logoColor=white" alt="Ollama" />
    <img src="https://img.shields.io/badge/Tailwind_CSS-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white" alt="Tailwind" />
    <img src="https://img.shields.io/badge/Framer_Motion-0055FF?style=for-the-badge&logo=framer&logoColor=white" alt="Framer Motion" />
  </div>
  <div style="margin-top: 5px;">
    <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker" />
    <img src="https://img.shields.io/badge/Zustand-443E38?style=for-the-badge&logo=react&logoColor=white" alt="Zustand" />
    <img src="https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react&logoColor=black" alt="React 19" />
    <img src="https://img.shields.io/badge/DeepFace-Biometrics-FF4500?style=for-the-badge" alt="DeepFace" />
  </div>
</div>

<br />
---

## 1. Project Overview & Philosophy

J.A.R.V.I.S is a modular, full-stack Open Source Intelligence (OSINT) and AI assistant platform. It goes beyond simple profile searching — it is a comprehensive intelligence workstation that combines automated web reconnaissance, agentic AI conversations, multimodal vision analysis, biometric face matching, psychological profiling, predictive analytics, and real-time target monitoring into a single unified interface.

When a user submits a search query (a person's name), J.A.R.V.I.S orchestrates parallel scraping, API querying, and AI synthesis across **15+ social media platforms**, developer ecosystems, corporate registries, data breach databases, and the open web. The result is a structured intelligence dossier complete with network graphs, geographic intelligence maps, social influence scores, sentiment analysis, and cross-validated findings.

Beyond search, J.A.R.V.I.S functions as an intelligent assistant:

- **Agent Mode** — An agentic AI that autonomously decides which OSINT tools to invoke during multi-turn conversations, reasoning through complex queries step by step.
- **Vision Analysis** — Multimodal image understanding powered by `llama3.2-vision`, capable of social media photo OSINT, screenshot OCR, and visual face comparison.
- **Face Matching** — Cross-platform biometric verification using DeepFace, comparing profile photos across discovered social accounts with confidence scoring.
- **User Memory** — A persistent context layer that remembers user preferences, facts, and interaction patterns across sessions, injected into every AI response for personalization.
- **Watch System** — Real-time monitoring of targets at configurable intervals (5 minutes to 24 hours), with automated change detection and diff reporting.
- **System Control** — Approval-gated command execution, application launching, and URL opening, with full audit trails.
- **Plugin Architecture** — Dynamic plugin discovery, toggle management, and manual execution for extending J.A.R.V.I.S capabilities.
- **Health Tracking** — Wellness telemetry with AI-powered suggestions and pattern detection.
- **Export System** — Generate classified-style PDF dossiers, structured JSON, or Maltego/i2-compatible CSV from any search result or saved profile.

The core philosophy of J.A.R.V.I.S centers on **data privacy and local execution**. All AI analysis runs entirely on your local machine using **Ollama** with dual models: `qwen3:8b` for text intelligence and `llama3.2-vision` for multimodal analysis. Queries, scraped contents, and results never leave your local network — data is persisted into a private SQLite database (or optionally PostgreSQL) under your full control.

---

## 2. Core Architecture & Stack Breakdown

J.A.R.V.I.S utilizes a decoupled frontend-backend architecture with 14 route groups, 22+ backend services, and a relational persistence layer.

```mermaid
graph TD;
    subgraph Frontend ["Next.js 15 + React 19 Frontend"]
        UI[Chat Interface] -->|Search Query + Depth| CHAT[Chat Terminal]
        UI -->|Agent Mode| AGENT[Agent Chat]
        UI -->|RAG Mode| RAG[RAG Panel]
        CHAT -->|Display| CARDS[Profile Card + Widgets]
        CARDS --> VIZ[NetworkGraph / GeoIntMap / Gauges]
        UI -->|Side Panels| PANELS[Memory / Watch / Plugins / System / Health]
    end

    subgraph Backend ["FastAPI Python Backend"]
        MW[Middleware: CORS + Rate Limit + Auth + Logging] --> ROUTES
        ROUTES[14 Route Groups / 55+ Endpoints]
        ROUTES --> ORCH[Search Orchestration]
        ORCH --> SS[Web Scraper]
        ORCH --> SC[Social Scraper]
        ORCH --> GH[GitHub API]
        ORCH --> BR[Breach Detection]
        ORCH --> DW[Dark Web Intel]
        ORCH --> CO[Company Records]
        ORCH --> GEO[GeoInt Service]
        ORCH --> FM[Face Matching]
        SS & SC & GH & BR -->|Context| AI["Ollama AI (qwen3:8b)"]
        AI -->|Structured JSON| ORCH
        ROUTES --> VIS["Vision Service (llama3.2-vision)"]
        ROUTES --> MEM[Memory Service]
        ROUTES --> WATCH[Watch Service]
        ROUTES --> SYS[System Control]
        ROUTES --> HEAL[Self-Healing Monitor]
        ROUTES --> PLG[Plugin Manager]
    end

    subgraph Persistence ["SQLite / PostgreSQL"]
        ORCH -->|SQLAlchemy ORM| DB[(profiles)]
        ORCH --> HIST[(search_history)]
        ORCH --> SNAP[(profile_snapshots)]
        MEM --> UMEM[(user_memories)]
    end

    Frontend <==>|"Axios HTTP + SSE Stream"| Backend
```

### 2.1 Backend Core (Python / FastAPI)

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Web Framework** | FastAPI 0.109+ | Async request handling, Pydantic validation, OpenAPI docs, lifespan context manager |
| **Middleware** | Custom stack | CORS, per-IP sliding-window rate limiting (30 req/60s), API key auth, request/response logging |
| **ORM** | SQLAlchemy 2.0 | Database abstraction, session pooling, model mapping for SQLite and PostgreSQL |
| **AI Client** | Ollama Python | Bridges async FastAPI with local LLM daemon — dual model support (text + vision) |
| **Scraping** | BeautifulSoup4 + Requests + httpx | DOM parsing, HTTP communication, async HTTP for Ollama connectivity checks |
| **Face Matching** | DeepFace 0.0.89 | Cross-platform biometric face comparison with confidence scoring |
| **Image Processing** | Pillow 10.0 | Image manipulation for vision analysis and face matching pipelines |
| **PDF Generation** | fpdf2 2.7 | Classified-style PDF dossier export with formatted sections |
| **Caching** | cachetools 5.3 | In-memory TTL cache for search results (5 min TTL, 50 query max) |
| **Self-Healing** | Background task | 30-second interval service health monitoring with auto-recovery |
| **Plugins** | Dynamic discovery | File-system based plugin loading, toggle state, manual execution |
| **Logging** | Rich 13.0 + Custom logger | Terminal-styled logging with SSE subscriber broadcast |

**Exception Handling:** Global handlers for `RequestValidationError` (422 with field-level detail) and unhandled exceptions (500 generic error) ensure consistent error response format across all 55+ endpoints.

### 2.2 Frontend Core (Next.js / TypeScript)

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Framework** | Next.js 15.1.6 + React 19 | App Router, SSR boundaries, error/loading/404 pages |
| **State Management** | Zustand 5.0.11 | Lightweight global store managing chat, RAG, agent, search, watches, memory, plugins, system actions, and health state |
| **Styling** | Tailwind CSS 3.4.17 | Utility-first dark-mode exclusive visual identity |
| **Animations** | Framer Motion 11 | Physics-based transitions, staggered renders, modal mounts |
| **Maps** | React-Leaflet 5.0 + Leaflet | Geographic intelligence visualization with location markers |
| **Graphs** | react-force-graph-2d 1.29 | Force-directed network relationship graphs |
| **Markdown** | React-Markdown 10.1 | AI response rendering with full markdown support |
| **Icons** | Lucide React 0.460 + Custom SVGs | UI icons + 15 custom brand icons (Spotify, TikTok, Steam, Discord, etc.) |
| **Notifications** | Sonner 2.0.7 | Toast notification system for success/error/warning feedback |
| **HTTP Client** | Axios 1.6 | API communication with 120s default / 300s search timeout |
| **Code Splitting** | Dynamic imports | Lazy-loaded heavy components: ProfileCard, FaceMatch, NetworkGraph, AgentChatMode |

### 2.3 Persistence Layer (SQLite / PostgreSQL)

**Default: SQLite** — Zero-configuration file-based database at `data/jarvis.db`. SQLAlchemy automatically creates all tables on first startup. No manual database setup required.

**Optional: PostgreSQL 16** — For production deployments requiring concurrent access and advanced indexing. Configure via `DATABASE_URL` in `.env`. PostgreSQL is specifically useful for its native `JSONB` support, allowing indexed queries over the semi-structured LLM output fields (`additional_info`, `similar_profiles`, `network_connections`).

Both backends share identical SQLAlchemy models and are fully interchangeable by changing a single environment variable.

---

## 3. The Multi-Stage Processing Pipeline

When a user initiates a search, J.A.R.V.I.S transitions through five pipeline stages. The depth and breadth of each stage is controlled by a user-selected **Depth Configuration** (1–10), which translates into concrete parameters via `depth_config.py`:

| Depth Range | Tier | Query Variations | Deep Scrapes | Behavior |
|-------------|------|-----------------|--------------|----------|
| 1–3 | `surface` | 2–3 | 1–2 | Fast scan, minimal scraping, basic social lookup |
| 4–6 | `medium` | 4–5 | 3–5 | Balanced depth, moderate web scraping, full social discovery |
| 7–10 | `deep` | 8–12 | 8–12 | Exhaustive reconnaissance, maximum scraping budget, extended timeouts |

### Stage 1: The Developer Index (`github_service.py`)

GitHub is the first point of contact, as many targets are software engineers or maintain public repositories.

1. **Direct Lookup:** Attempts an exact username query against `https://api.github.com/users/{name}`.
2. **Fuzzy Fallback:** On 404, the system queries `/search/users?q={name}&per_page=1` and extracts the highest-confidence match.
3. **Repository Interrogation:** Once a valid user is found, `/users/{username}/repos` pulls the top repositories sorted by `updated` timestamp.
4. **Contribution Analysis:** Extracts language distributions, star counts, and activity patterns.
5. **Context Formatting:** Raw JSON is converted into structured plaintext injected directly into the LLM context window.

### Stage 2: The Social Bypass Extractor (`scraper_service.py`)

Direct scraping of social platforms results in HTTP 403 blocks. J.A.R.V.I.S circumvents this via search-engine proxying across **15+ platforms**:

| Platform | Detection Method | URL Pattern |
|----------|-----------------|-------------|
| LinkedIn | Yahoo subspace + regex | `linkedin.com/in/{username}` |
| Instagram | Yahoo subspace + negative filter (`/p/`, `/reel/`, `/explore/`) | `instagram.com/{username}` |
| X (Twitter) | Yahoo subspace + regex | `twitter.com/{username}` or `x.com/{username}` |
| Spotify | Yahoo subspace + regex | `open.spotify.com/user/{id}` |
| TikTok | Yahoo subspace + regex | `tiktok.com/@{username}` |
| YouTube | Yahoo subspace + regex | `youtube.com/@{username}` or `/channel/{id}` |
| Reddit | Yahoo subspace + regex | `reddit.com/user/{username}` |
| Facebook | Yahoo subspace + regex | `facebook.com/{username}` |
| Pinterest | Yahoo subspace + regex | `pinterest.com/{username}` |
| Medium | Yahoo subspace + regex | `medium.com/@{username}` |
| Tumblr | Yahoo subspace + regex | `{username}.tumblr.com` |
| Snapchat | Yahoo subspace + regex | `snapchat.com/add/{username}` |
| Threads | Yahoo subspace + regex | `threads.net/@{username}` |
| Steam | Yahoo subspace + regex | `steamcommunity.com/id/{username}` |

**URL Unpacking:** Yahoo obfuscates URLs behind redirect strings (`/RU=https...`). J.A.R.V.I.S decodes these payloads using `urllib.parse.unquote` and applies platform-specific regex with negative filters to ensure only base profile URLs are captured.

Additionally, the scraper detects **mentions** (not direct profiles) for platforms that resist scraping: Tinder, Bumble, and Discord.

### Stage 3: The Deep Packet Infiltrator (`search_service.py`)

This service extracts the biographical text required to generate a dossier.

1. **Visual Authentication:** Queries the Wikipedia API (`en.wikipedia.org/w/api.php`) with the target name. Applies Unicode normalization (`unicodedata.normalize`) and case-insensitive subset matching to prevent name collisions. Only on perfect overlap does it pull a profile thumbnail.
2. **Multi-Vector Scraping:** Creates `num_query_variations` distinct search queries (Name + Biography, Name + Education, Name + Career, etc.) based on depth config. Grabs URLs per query with deduplication.
3. **Deep Document Parsing:** Targets the top URLs (explicitly filtering out social media sites). Downloads raw DOM and recursively decomposes `<script>`, `<style>`, `<header>`, and `<nav>` tags.
4. **Sanitization:** Extracts semantic text (`<p>`, `<h1>`, `<h2>` tags), strips whitespace, and truncates to a dense character budget scaled by depth.

### Stage 4: Local AI Synthesis (`ai_service.py`)

All formatted data from Stages 1–3 is compacted into a single prompt and sent to the local Ollama instance (`qwen3:8b`).

1. **System Prompt:** The AI is given a restrictive identity, commanded to produce structured analysis covering: biographical summary, professional trajectory, psychological profile, controversy assessment, influence network mapping, social engineering vectors, and future trajectory predictions.
2. **Hallucination Prevention:** The prompt explicitly instructs: *"You MUST ONLY write about the exact requested person. If the search context is about a CLEARLY DIFFERENT person, you MUST IGNORE that context entirely."*
3. **Psychological Analysis:** Generates personality trait vectors, communication style assessment, and social engineering vulnerability profiles via `psychological_analysis_service.py`.
4. **Predictive Analysis:** Produces behavioral forecasts across four time horizons (24h, 7d, 30d, 90d) with probability scores via `predictive_analysis_service.py`.
5. **Cross-Validation:** Compares data points across sources to flag inconsistencies and rate confidence levels.
6. **JSON Structuring:** A second lightweight AI pass restructures the raw dossier into a strictly formatted JSON payload for frontend ingestion.

### Stage 5: Post-Processing & Enrichment

After AI synthesis, parallel enrichment services activate based on depth configuration:

| Service | Source | Data Produced |
|---------|--------|---------------|
| **Face Matching** (`face_matching_service.py`) | DeepFace library | Cross-platform biometric comparison with confidence percentages |
| **Breach Detection** (`breach_service.py`) | XposedOrNot API | Email-linked data breaches — breach name, date, affected count, exposed data classes |
| **Dark Web Intel** (`darkweb_service.py`) | Paste site scraping | Credential exposure, paste records, leak aggregation |
| **Company Records** (`company_service.py`) | OpenCorporates, SEC EDGAR, Companies House, KAP.org.tr | Corporate affiliations, officer roles, filing history |
| **Geographic Intelligence** (`geoint_service.py`) | EXIF extraction, IP geolocation | Location coordinates, timezone analysis, activity pattern inference |
| **Social Scoring** (`social_score_service.py`) | Algorithmic analysis | Platform influence scores, activity metrics, cross-platform presence rating |

---

## 4. Feature Highlights

### 4.1 Agent Mode

The Agent Mode transforms J.A.R.V.I.S from a search tool into an autonomous AI assistant. When enabled, the AI dynamically decides which OSINT tools to invoke based on the user's natural language query.

- **Multi-Turn Conversations:** Maintains conversation context across messages, allowing follow-up questions and iterative refinement.
- **Tool Selection:** The agent inspects available tools (`GET /api/agent/tools`) and selects the appropriate ones — search, scrape, analyze, compare — without manual intervention.
- **Streaming Responses:** Results stream token-by-token to the frontend via SSE, providing real-time feedback as the agent reasons and acts.

### 4.2 Vision Analysis

Four distinct vision modes powered by `llama3.2-vision` running locally via Ollama:

| Mode | Endpoint | Purpose |
|------|----------|---------|
| General Analysis | `POST /api/vision/analyze` | Open-ended image understanding with custom prompts |
| Social Photo OSINT | `POST /api/vision/social-photo` | Extract intelligence from social media photos — location clues, companions, activities, metadata |
| Screenshot OCR | `POST /api/vision/screenshot` | Text extraction and content understanding from screenshots |
| Face Comparison | `POST /api/vision/compare-faces` | Visual similarity assessment between two face images |

### 4.3 Face Matching

Cross-platform biometric verification using the DeepFace library:

- Compares profile photos discovered across social media accounts during the search pipeline.
- Returns confidence percentages and match/no-match verdicts.
- Supports multiple pose angles and lighting conditions.
- Results displayed in the `FaceMatch.tsx` widget with expandable comparison details.

### 4.4 RAG Chat

Retrieval-Augmented Generation allows conversational Q&A over search results:

- After a search completes, users can ask follow-up questions about the discovered profile.
- The RAG system injects the full search context (dossier, social links, breach data) into the AI prompt.
- User memory context is automatically included for personalized responses.
- Responses stream in real-time via `RagStreamingBubble.tsx`.

### 4.5 User Memory

A persistent context layer that makes J.A.R.V.I.S remember:

| Category | Purpose | Example |
|----------|---------|---------|
| `preference` | User preferences and settings | "Prefers Turkish language responses" |
| `fact` | Factual information about the user | "Works at Company X as a security analyst" |
| `interaction` | Interaction patterns | "Usually searches for cybersecurity professionals" |
| `personality` | Personality traits | "Technical communication style, prefers concise answers" |

Memories are ranked by importance (1–10), support semantic keyword search, and are automatically injected into AI context for every response. Full CRUD operations available via the Memory Panel.

### 4.6 Watch System

Real-time target monitoring with automated change detection:

- **Configurable Intervals:** Monitor targets every 5 minutes to 24 hours.
- **Change Detection:** Compares current scan results against previous snapshots, highlighting new social accounts, updated descriptions, or changed metrics.
- **Bulk Management:** Start, stop, or stop-all active watches from the Watch Panel.
- **History:** View all detected changes over time for any monitored target.

### 4.7 Plugin System

Extensible architecture for adding custom capabilities:

- **Discovery:** J.A.R.V.I.S scans the `app/plugins/` directory on startup and registers all valid plugins.
- **Toggle:** Enable or disable plugins at runtime without restart.
- **Execution:** Manually trigger any enabled plugin from the Plugin Panel.

### 4.8 System Control

Approval-gated operating system interaction:

- **Command Execution:** Request shell commands — each enters a `pending` state requiring explicit user approval before execution.
- **Application Launching:** Open applications by name with the same approval workflow.
- **URL Opening:** Open URLs in the default browser, also approval-gated.
- **Audit Trail:** Full history of all requested, approved, denied, and executed actions.
- **Security:** Computer control is disabled by default (`enable_computer_control = False`). Must be explicitly enabled in `.env`.

### 4.9 Health Tracking

Wellness telemetry integrated into the assistant:

- **Categories:** Predefined health categories (sleep, exercise, stress, nutrition, etc.).
- **Recording:** Log data points with timestamps from the Health Panel.
- **AI Suggestions:** Request AI-powered health recommendations based on recorded patterns.
- **Pattern Detection:** Automated analysis of health data trends over time.

### 4.10 Export System

Three export formats for every search result or saved profile:

| Format | Style | Use Case |
|--------|-------|----------|
| **PDF** | Classified intelligence dossier layout | Formal reporting, archival |
| **JSON** | Structured data with all fields | API consumption, data pipelines |
| **CSV** | Maltego/i2 Analyst Notebook compatible | Integration with professional OSINT tools |

Exports work on both **saved profiles** (by ID) and **live search results** (by POST payload with 1 MB body limit).

### 4.11 Version History

Profile evolution tracking across repeated searches:

- **Snapshots:** Every search creates an immutable snapshot of the discovered profile state.
- **Change Reports:** Compare the two most recent snapshots to see what changed — new social accounts, updated descriptions, modified metrics.
- **Timeline View:** Browse all historical snapshots for any previously searched person.
- **Displayed via** the `VersionHistory.tsx` widget with diff highlighting.

---

## 5. Database Schema Deep Dive

J.A.R.V.I.S uses 4 tables managed by SQLAlchemy ORM. All tables are auto-created on first startup — no manual schema initialization required for SQLite.

### `profiles`

The primary data store for completed intelligence dossiers.

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| `id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | Unique record identifier |
| `name` | `VARCHAR(255)` | `NOT NULL`, `INDEXED` | Search target name, B-Tree indexed for fast retrieval |
| `github_url` | `TEXT` | `NULL` | Verified GitHub profile URL |
| `instagram_url` | `TEXT` | `NULL` | Instagram profile URL |
| `twitter_url` | `TEXT` | `NULL` | X / Twitter profile URL |
| `linkedin_url` | `TEXT` | `NULL` | LinkedIn profile URL |
| `spotify_url` | `TEXT` | `NULL` | Spotify profile URL |
| `tiktok_url` | `TEXT` | `NULL` | TikTok profile URL |
| `snapchat_url` | `TEXT` | `NULL` | Snapchat profile URL |
| `tumblr_url` | `TEXT` | `NULL` | Tumblr blog URL |
| `youtube_url` | `TEXT` | `NULL` | YouTube channel URL |
| `reddit_url` | `TEXT` | `NULL` | Reddit profile URL |
| `facebook_url` | `TEXT` | `NULL` | Facebook profile URL |
| `pinterest_url` | `TEXT` | `NULL` | Pinterest profile URL |
| `medium_url` | `TEXT` | `NULL` | Medium profile URL |
| `threads_url` | `TEXT` | `NULL` | Threads profile URL |
| `steam_url` | `TEXT` | `NULL` | Steam profile URL |
| `tinder_mention` | `TEXT` | `NULL` | Tinder mention (non-direct) |
| `bumble_mention` | `TEXT` | `NULL` | Bumble mention (non-direct) |
| `discord_mention` | `TEXT` | `NULL` | Discord mention (non-direct) |
| `description` | `TEXT` | `NULL` | Full AI-generated intelligence dossier (1,500+ words) |
| `additional_info` | `JSON` | `NULL` | Dynamic nested objects — raw metrics, scores, analysis data |
| `similar_profiles` | `JSON` | `NULL` | Array of related/similar profile identifiers |
| `cross_validation_issues` | `JSON` | `NULL` | Flagged inconsistencies across data sources |
| `network_connections` | `JSON` | `NULL` | Mapped relationship network |
| `email_addresses` | `JSON` | `NULL` | Discovered email addresses |
| `data_breaches` | `JSON` | `NULL` | Breach records from XposedOrNot |
| `created_at` | `TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP` | Record creation time |
| `updated_at` | `TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP` | Last modification time |

### `search_history`

Tracks recent search queries with automatic 7-day expiration.

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| `id` | `INTEGER` | `PRIMARY KEY` | Unique identifier |
| `query_name` | `VARCHAR(255)` | `NOT NULL`, `INDEXED` | The searched name |
| `searched_at` | `TIMESTAMP` | `INDEXED`, `DEFAULT CURRENT_TIMESTAMP` | Search timestamp; records older than 7 days are auto-deleted |

### `profile_snapshots`

Immutable point-in-time captures for version history and change detection.

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| `id` | `INTEGER` | `PRIMARY KEY` | Unique identifier |
| `query_name` | `VARCHAR(255)` | `NOT NULL`, `INDEXED` | Normalized target name |
| `github_url` ... `tiktok_url` | `TEXT` | `NULL` | Snapshot of social URLs at capture time |
| `description` | `TEXT` | `NULL` | Dossier text at capture time |
| `additional_info` | `JSON` | `NULL` | Metrics snapshot |
| `snapshot_data` | `JSON` | `NULL` | Flexible additional data |
| `captured_at` | `TIMESTAMP` | `INDEXED`, `DEFAULT CURRENT_TIMESTAMP` | Snapshot creation time |

### `user_memories`

Persistent user context for AI personalization.

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| `id` | `INTEGER` | `PRIMARY KEY` | Unique identifier |
| `category` | `VARCHAR(50)` | `NOT NULL`, `INDEXED` | One of: `preference`, `fact`, `interaction`, `personality` |
| `key` | `VARCHAR(255)` | `NOT NULL`, `INDEXED` | Memory identifier (e.g., "language_preference") |
| `value` | `TEXT` | `NOT NULL` | Memory content |
| `context` | `TEXT` | `NULL` | Optional additional context |
| `importance` | `INTEGER` | `DEFAULT 5` | Priority ranking from 1 (low) to 10 (critical) |
| `created_at` | `TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP` | Creation time |
| `updated_at` | `TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP` | Last update time |

---

## 6. User Interface Architecture

The Next.js frontend is a fully componentized single-page application with dynamic imports for performance optimization.

### 6.1 Core Chat System

| Component | Role |
|-----------|------|
| `ChatInterface.tsx` | Master orchestrator — manages SSE connections for live backend status, coordinates search flow, renders profile results and analysis widgets |
| `ChatInputBar.tsx` | Search input with integrated depth selector (1–10), vision upload button, and agent mode toggle |
| `StreamingMessageBubble.tsx` | Displays AI responses as they stream token-by-token via SSE |
| `RagStreamingBubble.tsx` | RAG-specific streaming display for follow-up Q&A |
| `RagInteractionPanel.tsx` | Full RAG chat interface with document context display |
| `AgentChatMode.tsx` | Multi-turn agent conversation interface with tool invocation visibility |
| `LiveStatusMonitor.tsx` | Real-time backend activity feed showing scraping progress, API calls, and AI inference status |
| `LoadingIndicator.tsx` | Custom animated loading states |

### 6.2 Profile Visualization & Analysis Widgets

| Component | Visualization |
|-----------|---------------|
| `ProfileCard.tsx` | Comprehensive profile display — markdown rendering, 15+ social link icons, export buttons (PDF/JSON/CSV), expandable sections |
| `NetworkGraph.tsx` | Force-directed relationship graph using `react-force-graph-2d` — interactive nodes representing connections, affiliations, and influence pathways |
| `GeoIntMap.tsx` | Geographic intelligence map using `react-leaflet` — location markers, activity zones, inferred locations from timezone analysis |
| `SecurityScanWidget.tsx` | Data breach visualization — breach timeline, exposed data classes, paste site records, severity indicators |
| `FaceMatch.tsx` | DeepFace biometric results — side-by-side photo comparison, confidence percentages, match/partial/unverified verdicts |
| `SocialGauge.tsx` | Social media presence scoring — platform spread, activity metrics, influence rating |
| `SentimentGauge.tsx` | Sentiment analysis visualization — positive/negative/neutral distribution across discovered content |
| `PsychologicalAnalysisWidget.tsx` | Personality profile — trait vectors, communication style, social engineering vulnerability assessment |
| `PredictiveAnalysisWidget.tsx` | Behavioral forecasting — predictions across 24h/7d/30d/90d horizons with probability scores |
| `VersionHistory.tsx` | Profile change tracking — diff highlighting between snapshots, timeline view |

### 6.3 Side Panel System

The `HistorySidebar.tsx` component provides a tabbed interface for managing all auxiliary features:

| Panel | Component | Functions |
|-------|-----------|-----------|
| **History** | Built into sidebar | Browse, re-search, and delete past searches |
| **Memory** | `MemoryPanel.tsx` | Create, browse, search, and delete user memories by category |
| **Watch** | `WatchPanel.tsx` | Start/stop target monitoring, view active watches and detected changes |
| **Plugins** | `PluginPanel.tsx` | Toggle plugins on/off, manually trigger execution, view plugin metadata |
| **System** | `SystemPanel.tsx` | Review pending actions, approve/deny command execution, browse action history |
| **Health** | `HealthPanel.tsx` | Record health data, view history, request AI suggestions, detect patterns |

### 6.4 Visual Design System

| Component | Effect |
|-----------|--------|
| `Background.tsx` | Aurora glow effects, animated scan lines, grid overlay, floating arc reactor elements |
| `ScrambleText.tsx` | Glitchy text scramble animation for terminal aesthetic |
| `GlitchText.tsx` | Distortion text effect for emphasis |
| `CountUp.tsx` | Animated number counter for statistics |
| `Icons.tsx` | 15 custom SVG brand icons — Spotify, TikTok, Snapchat, Tumblr, Tinder, Bumble, YouTube, Reddit, Facebook, Pinterest, Medium, Threads, Steam, Discord, Phone |
| `LoadingAnimation.tsx` | Full-page loading animation during initial app load |
| `ErrorBoundary.tsx` | React error boundary for graceful failure recovery |

---

## 7. Deployment Guide

### 7.1 Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| **Python** | 3.11+ | For `asyncio` and modern type hints |
| **Node.js** | 18.17+ | For Next.js 15 compilation |
| **Ollama** | Latest | **Required** — must be running before starting J.A.R.V.I.S |
| **SQLite** | Built-in | No installation needed — ships with Python |
| **PostgreSQL** | 16 (optional) | Only if you need concurrent access or production deployment |

### 7.2 Quick Start (Automated)

The project provides launcher scripts that handle everything automatically:

**Windows:**
```cmd
start-jarvis.bat
```

**macOS / Linux:**
```bash
chmod +x start-jarvis.sh
./start-jarvis.sh
```

The launcher scripts perform these steps:
1. Verify Ollama is running (exits with error if not)
2. Create Python virtual environment if missing
3. Install backend dependencies (`pip install -r requirements.txt`)
4. Create `.env` from `.env.example` if missing
5. Create `data/` directory for SQLite database
6. Install frontend dependencies (`npm install`)
7. Clear `.next` build cache
8. Kill existing processes on ports 8000 and 3000
9. Start FastAPI backend on port 8000
10. Start Next.js frontend on port 3000
11. Open browser to `http://localhost:3000`

### 7.3 Docker Deployment

A `docker-compose.yml` is provided for containerized deployment with three services:

```bash
docker-compose up -d
```

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| `backend` | Custom (Python 3.11) | 8000 | FastAPI server |
| `frontend` | Custom (Node 20) | 3000 | Next.js application |
| `ollama` | `ollama/ollama` | 11434 | Local LLM engine |

After containers are up, pull the required AI models:
```bash
docker exec -it <ollama-container-name> ollama pull qwen3:8b
docker exec -it <ollama-container-name> ollama pull llama3.2-vision
```

Data persists via Docker volumes: `backend/data` for SQLite and `ollama_data` for model weights.

### 7.4 Manual Setup

#### Step 1: Install and Start Ollama
Download from [ollama.ai](https://ollama.ai) and pull the required models:
```bash
ollama pull qwen3:8b
ollama pull llama3.2-vision
```

#### Step 2: Backend
```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env    # Edit .env as needed
mkdir data              # SQLite storage directory
python -m app.main
```

#### Step 3: Frontend
```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000` in your browser.

### 7.5 Configuration Reference (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./data/jarvis.db` | Database connection string. Use `postgresql://user:pass@host:5432/jarvis` for PostgreSQL |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama daemon address |
| `OLLAMA_MODEL` | `qwen3:8b` | Primary text model for intelligence synthesis |
| `VISION_MODEL` | `llama3.2-vision` | Multimodal vision model |
| `GITHUB_TOKEN` | *(empty)* | Optional GitHub Personal Access Token for increased API rate limits |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |
| `API_KEY` | *(empty)* | API key for endpoint authentication. **Empty = auth disabled** |
| `RATE_LIMIT_REQUESTS` | `30` | Max requests per sliding window per IP |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Sliding window duration in seconds |
| `ENABLE_COMPUTER_CONTROL` | `False` | Enable system command execution (disabled by default for security) |
| `DEBUG` | `False` | Enable debug/test endpoints |
| `PLUGINS_DIR` | `app/plugins` | Plugin discovery directory |
| `SEARCH_CACHE_TTL_SECONDS` | `300` | Search result cache TTL (5 minutes) |
| `SEARCH_CACHE_MAX_SIZE` | `50` | Maximum cached search queries |

Frontend environment (`.env.local`):
| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend API URL |
| `NEXT_PUBLIC_API_KEY` | *(empty)* | API key (must match backend `API_KEY`) |

---

## 8. FastAPI Endpoint Mapping

The `routes/` directory manages all external HTTP interfacing across 14 route groups and 55+ endpoints.

### Search (`/api/search`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/` | Execute full search pipeline. **Payload:** `{"query": "Name", "depth": 5}`. Long-polling blocking call — returns structured `ProfileResponse` JSON when complete. |
| `GET` | `/test` | Health check for the search subsystem. |
| `GET` | `/test-scraper` | Debug endpoint for raw scraper output (requires `debug=true` in config). |

### Profiles (`/api/profiles`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/` | Save a profile to the database. **Payload:** `ProfileCreate` Pydantic model. |
| `GET` | `/` | List all saved profiles with pagination (`skip`, `limit`). |
| `GET` | `/{profile_id}` | Retrieve a single profile by ID. |
| `DELETE` | `/{profile_id}` | Delete a profile by ID. |
| `GET` | `/search/{name}` | Fast database lookup using SQL `ILIKE %name%` — bypasses the AI pipeline. |

### History (`/api/history`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | List all search history (deduplicated, newest first; auto-deletes entries older than 7 days). |
| `DELETE` | `/{history_id}` | Delete a single history entry. |
| `DELETE` | `/` | Clear all search history. |

### Chat (`/api/chat`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/` | RAG-based streaming response. **Payload:** `{"query_name": "Name", "messages": [...]}`. Injects user memory context automatically. |

### Agent (`/api/agent`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/chat` | Agentic AI chat — the model decides which tools to call. Supports streaming responses. |
| `GET` | `/tools` | List all available OSINT tools the agent can invoke. |

### Export (`/api/export`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/pdf/{profile_id}` | Export saved profile as classified-style PDF dossier. |
| `GET` | `/json/{profile_id}` | Export saved profile as structured JSON. |
| `GET` | `/csv/{profile_id}` | Export saved profile as Maltego/i2-compatible CSV. |
| `POST` | `/pdf` | Export live search result as PDF. **Body limit:** 1 MB. |
| `POST` | `/json` | Export live search result as JSON. **Body limit:** 1 MB. |
| `POST` | `/csv` | Export live search result as CSV. **Body limit:** 1 MB. |

### Face Match (`/api/face-match`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/compare` | Compare face images from provided URLs using DeepFace backend. Returns confidence score and match verdict. |

### Memory (`/api/memory`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/` | Store or update a user memory. **Payload:** `{"category": "...", "key": "...", "value": "...", "importance": 5}`. |
| `GET` | `/` | Recall all memories (filter by `category` or `key` query params). |
| `GET` | `/context` | Get the full user context string for AI injection. |
| `POST` | `/search` | Semantic keyword search through stored memories. |
| `DELETE` | `/{memory_id}` | Delete a specific memory by ID. |
| `DELETE` | `/category/{category}` | Delete all memories in a given category. |

### Health (`/api/health`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/categories` | List all available health tracking categories. |
| `POST` | `/record` | Record a health data point (category, value, timestamp). |
| `GET` | `/history` | Get health history with pagination and category filtering. |
| `POST` | `/suggestions` | Get AI-powered health suggestions based on recorded data. |
| `GET` | `/patterns` | Detect patterns and trends in health data. |

### System (`/api/system`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/execute/command` | Request shell command execution (enters `pending` approval state). |
| `POST` | `/execute/app` | Request application launch (enters `pending` approval state). |
| `POST` | `/execute/url` | Request URL opening (enters `pending` approval state). |
| `POST` | `/approve` | Approve a pending action by ID — triggers execution. |
| `POST` | `/deny` | Deny a pending action by ID. |
| `GET` | `/pending` | List all actions awaiting approval. |
| `GET` | `/history` | Get full action history (requested, approved, denied, executed, failed). |
| `GET` | `/service-status` | Get real-time status of all monitored backend services. |
| `GET` | `/health-log` | Get self-healing service activity log. |

### Vision (`/api/vision`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/analyze` | General-purpose image analysis with custom prompts. |
| `POST` | `/social-photo` | OSINT-focused social media photo analysis — extract location clues, companions, activities. |
| `POST` | `/screenshot` | OCR-like text extraction and content understanding from screenshots. |
| `POST` | `/compare-faces` | Visual face comparison between two provided images. |

### Watch (`/api/watch`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/start` | Start monitoring a target. **Payload:** `{"query": "Name", "interval_minutes": 60}` (5–1440 min range). |
| `POST` | `/stop` | Stop monitoring a specific target. |
| `POST` | `/stop-all` | Stop all active monitoring tasks. |
| `GET` | `/` | List all currently active watches. |
| `GET` | `/{query}` | Get detailed status and change history for a specific watch. |

### Plugins (`/api/plugins`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | List all discovered plugins with metadata and enabled state. |
| `POST` | `/{name}/toggle` | Toggle a plugin's enabled/disabled state. |
| `POST` | `/{name}/run` | Manually execute a specific plugin. |

### Version History (`/api/version-history`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/{query_name}` | Get all profile snapshots for a person (oldest to newest). |
| `GET` | `/{query_name}/report` | Get a change report comparing the two most recent snapshots. |

### Root Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | API metadata — version, status, key endpoint paths. |
| `GET` | `/api/status/stream` | SSE stream for live J.A.R.V.I.S activity logs. |
| `GET` | `/health` | Comprehensive health check — returns status of all dependent services (Ollama, database, plugins, self-healing). |

---

## 9. Security & Middleware

J.A.R.V.I.S implements a layered security architecture:

| Layer | Implementation | Details |
|-------|----------------|---------|
| **API Key Authentication** | `verify_api_key` dependency | Optional `X-API-Key` header validation. Disabled when `API_KEY` is empty. Startup warning logged when unprotected. |
| **Rate Limiting** | `RateLimitMiddleware` | Per-IP sliding window — 30 requests per 60 seconds by default. Exempts `/health`, `/docs`, `/openapi.json`, `/redoc`. |
| **CORS** | FastAPI `CORSMiddleware` | Configurable origins (default: `http://localhost:3000`). Allows all methods and headers. |
| **System Control Approval** | Approval workflow | Every command/app/URL execution request enters `pending` state. Requires explicit `approve` call before execution. Full audit trail maintained. |
| **Request Logging** | Custom middleware | Logs all incoming requests and outgoing responses with timing. Skips SSE streams to prevent log spam. |
| **Global Error Handling** | Exception handlers | Consistent JSON error format: `RequestValidationError` → 422 with field details; unhandled → 500 generic. |
| **Self-Healing** | Background monitor | 30-second interval health checks on dependent services (Ollama, database). Auto-recovery attempts on failure detection. |

---

## 10. Known Bottlenecks and Constraints

1. **Scraper Flagging:** Repeated requests via `scraper_service.py` against Yahoo SERPs in short intervals will temporarily IP-ban your network. Use moderate depth settings (4–6) for repeated searches, or increase delays between batch queries.
2. **First-Load VRAM Transfer:** Ollama unloads idle models from memory. The first query of any session experiences a lag while model weights transfer from SSD to GPU/CPU memory. Subsequent queries are fast.
3. **Vision Model Memory:** The `llama3.2-vision` model requires significant VRAM. Running both text and vision models simultaneously may exceed available GPU memory on systems with less than 8 GB VRAM.
4. **Rate Limiting State:** Rate limit counters are stored in-memory (`dict[str, list[float]]`). Server restarts reset all counters. Multi-instance deployments do not share rate limit state.
5. **DeepFace First Load:** The DeepFace library downloads face detection model files on first use, which may cause a one-time delay during the initial face matching request.

---

## 11. Licensing

This project is open-source under the **MIT License**. It was developed strictly for OSINT, portfolio compilation, and development automation.

System operators are fully responsible for ensuring their usage of automated scraping scripts complies with all target platforms' `robots.txt` specifications and Terms of Service constraints.

---

## 12. Engineering Lead

**Yigit Erdogan** - System Architecture, Full-Stack Deployment, Model Tuning.

- **LinkedIn:** [yigit-erdogan-ba7a64294](https://www.linkedin.com/in/yi%C4%9Fit-erdo%C4%9Fan-ba7a64294)
- **Reddit:** [u/Yigtwx6](https://www.reddit.com/user/Yigtwx6/)
- **GitHub:** [Yigtwxx](https://github.com/Yigtwxx)
