# J.A.R.V.I.S: The Ultimate AI-Powered Open Source Intelligence (OSINT) Framework

<div align="center">
  <img src="https://img.shields.io/badge/J.A.R.V.I.S-OSINT%20Framework-00f3ff?style=for-the-badge&logo=probot&logoColor=white" alt="JARVIS OSINT System" />
  
  <p><strong>Just A Rather Very Intelligent System</strong></p>
  <p><em>A deeply integrated, full-stack, automated intelligence and profile synthesis architecture.</em></p>

  <div>
    <img src="https://img.shields.io/badge/Python-3.11+-blue?style=for-the-badge&logo=python" alt="Python" />
    <img src="https://img.shields.io/badge/FastAPI-0.109+-009688?style=for-the-badge&logo=fastapi" alt="FastAPI" />
    <img src="https://img.shields.io/badge/Next.js-15-black?style=for-the-badge&logo=next.js" alt="Next.js" />
    <img src="https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white" alt="TypeScript" />
  </div>
  <div style="margin-top: 5px;">
    <img src="https://img.shields.io/badge/PostgreSQL-16-336791?style=for-the-badge&logo=postgresql" alt="PostgreSQL" />
    <img src="https://img.shields.io/badge/Ollama-Local_LLM-FF6347?style=for-the-badge&logo=ollama&logoColor=white" alt="Ollama" />
    <img src="https://img.shields.io/badge/Tailwind_CSS-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white" alt="Tailwind" />
    <img src="https://img.shields.io/badge/Framer_Motion-0055FF?style=for-the-badge&logo=framer&logoColor=white" alt="Framer Motion" />
  </div>
</div>

---

## 📖 1. The Global Concept

J.A.R.V.I.S was created to solve a complex engineering and human resourcing problem: **Manual Data Aggregation.**

When researching a person—whether for hiring, reporting, or general curiosity—information is often siloed. A developer's technical skill lies on GitHub. Their visual identity is on Instagram or Wikipedia. Their professional history is locked behind LinkedIn. Identifying and synthesizing this data requires significant human willpower.

J.A.R.V.I.S automates this entirely. You provide a single input (e.g., `Linus Torvalds`), and the system spins up multiple concurrent network threads. It bypasses conventional search engine restrictions, scrapes raw HTML, cleans it, extracts vital nodes, and streams this massive corpus of unstructured text directly into a locally hosted **Large Language Model (LLM)**. The LLM acts as the central brain—parsing context, ignoring hallucinations, and formatting a strict, professional 10-section intelligence dossier stored in a PostgreSQL database.

Everything runs locally. Your data, your searches, and your AI remain entirely confidential on your host machine. No external SaaS APIs (like OpenAI) are required.

---

## 🏗️ 2. Extensive Architectural Breakdown

The project follows a decoupling principle, broken strictly into three layers:
1. **The Presentation Layer:** `Next.js 15`
2. **The Logic & Ingestion Layer:** `FastAPI` (Python)
3. **The Data Persistence Layer:** `PostgreSQL 16`

### 2.1 The Codebase Topology

```text
J.A.R.V.I.S/
├── backend/                  # The Python Intelligence Engine
│   ├── app/
│   │   ├── config.py         # Parses strict local .env variables
│   │   ├── main.py           # The FastAPI application core and CORS router
│   │   ├── jarvis_logger.py  # Custom CLI formatting engine for terminal feedback
│   │   ├── database/         # Connection pooling and SQLAlchemy engine
│   │   ├── models/           # SQLAlchemy class mappings (SQL Tables)
│   │   ├── schemas/          # Pydantic validation (In/Out HTTP models)
│   │   ├── routes/           # REST Controllers
│   │   │   ├── search.py     # Main Search Trigger
│   │   │   └── history.py    # Database retrieval logic
│   │   ├── services/         # The Heavy Lifters (Scrapers & AI)
│   │   │   ├── ai_service.py       # Ollama integration
│   │   │   ├── github_service.py   # GitHub API interactor
│   │   │   ├── scraper_service.py  # Regex social media extractor
│   │   │   └── search_service.py   # Yahoo + Wikipedia Deep Web parser
│   └── requirements.txt
│
├── frontend/                 # The React User Interface
│   ├── app/                  # Next.js App Router definitions
│   │   ├── page.tsx          # Main entry layout
│   │   ├── globals.css       # Global Tailwind directives
│   ├── components/           # Atomic React Components
│   │   ├── ApprovalDialog.tsx   # Modal for saving generated profiles
│   │   ├── Background.tsx       # The customized Iron Man Arc Reactor SVG
│   │   ├── ChatInterface.tsx    # The core interactive terminal
│   │   ├── LoadingAnimation.tsx # Spinner components
│   │   └── ProfileCard.tsx      # The actual Markdown dossier renderer
│   ├── services/             # Axios API wrappers
│   └── types/                # Typescript specific definitions
│
├── database/                 # SQL
│   └── init.sql              # The primary table schema execution script
├── start-jarvis.bat          # Windows Setup Executable
└── start-jarvis.sh           # Unix Setup Executable
```

---

## ⚙️ 3. Inside the Core Python Services (How it ACTUALLY works)

The magic of J.A.R.V.I.S lies inside the `backend/app/services/` directory. When `search.py` is invoked via a POST request, it sequentially yields to four services.

### 🕵️ 3.1 `github_service.py` - The Code Footprint Locator
Because tech profiles are often requested, GitHub gives the purest signal of a developer's identity.
*   **Mechanics:** The class initializes a `requests.Session` pointing to `api.github.com`. It attempts a direct `GET` to `/users/{requested_name}`. If that `404`s, the engine is smart enough to fallback to a fuzzy query (`/search/users?q={name}`) and grabs the exact `login_id` of the first match.
*   **Data Extraction:** Once the `login_id` is locked, the service grabs the target's public email, company, location, and follower counts. It then fires a sub-query to `/users/{username}/repos`, sorting by `updated_at`, extracting the top 5 raw repositories.
*   **Result:** It formats this into a raw context string for the AI: *"GitHub Profile: [url], Public Repos: 41, Top Repo: Linux (C) - 150K Stars."*

### 🌐 3.2 `scraper_service.py` - The Social Matrix Bypass
Directly making requests to `instagram.com` or `linkedin.com` using Python results in HTTP 403 blocks. To circumvent corporate scraping limits, this service uses Yahoo! Search.
*   **Mechanics:** When the script hunts for a LinkedIn URL, it formats a query: `requests.utils.quote(f"{name} linkedin")` and passes it to `search.yahoo.com`.
*   **DOM Traversal:** `BeautifulSoup4` traverses the `html.parser` structure hunting for all `<a href>` tags.
*   **De-obfuscation:** Yahoo hides direct links behind routing layers (`/RU=https...`). The script uses Python's `urllib.parse.unquote` to split the URI and isolate the pure outbound link.
*   **Regex Trapping (The Secret Sauce):** The service passes the pure links against strict Regex engines. 
    *   For Instagram: `r'instagram\.com/([a-zA-Z0-9._]+)'`. To avoid grabbing random posts, it explicitly rejects handles matching `"p"`, `"reel"`, `"explore"`, resolving to a pure `https://instagram.com/handle/` object.

### 📚 3.3 `search_service.py` - The Deep Web Packet Extractor
This is the most aggressive service in the backend, responsible for extracting the actual biographical text required to write a dossier.
*   **Visual Authentication Constraint:** It queries the Wikipedia API (`en.wikipedia.org/w/api.php`) with the target name. To stop "Name Collisions" (e.g., matching a politician instead of a developer), it converts both strings to lowercase arrays (`query_words_norm.issubset(title_words_norm)`) and removes all Unicode accents (`unicodedata.normalize`). Only if the set perfectly overlaps does it pull an 800px profile thumbnail.
*   **Corpus Expansion:** The script creates 5 distinct search queries (Name + Biography, Name + Education, etc.). It grabs 5 URLs per query, deduplicating them.
*   **Deep Scraping (`fetch_content`):** It targets the top 4 URLs (explicitly avoiding social media sites like Facebook). It downloads the raw DOM and executes `element.decompose()` recursively on all `<script>`, `<style>`, `<header>`, and `<nav>` tags. 
*   **Sanitization:** It extracts purely the `<p>`, `<h1>` and semantic text, strips white spaces, truncates it to the first 8,000 dense characters, and returns a massive text blob.

### 🧠 3.4 `ai_service.py` - The Synthetic Orchestrator (Local LLM)
This is where unstructured garbage text becomes pure intelligence.
*   **The Model:** Uses `ollama` Python bindings. It interfaces via API with whatever model `app/config.py` specifies (default is `llama3` 8B parameter).
*   **The Mega-Prompt:** The `_build_prompt` function merges all the raw text from Services 3.1, 3.2, and 3.3. It prepends an aggressive system instruction:
    *   *“You are JARVIS, an Elite Strategic Intelligence Analyst... Format the intelligence dossier into ALL of these sections... STRATEGIC BIOGRAPHY, PSYCHOLOGICAL PROFILE, NOTABLE ACHIEVEMENTS...”*
    *   *“CRITICAL RESTRICTION: You MUST ONLY write about the exact requested person. If the search context is about a CLEARLY DIFFERENT person, you MUST IGNORE that context entirely.”*
*   **The JSON Pass:** The AI outputs a massive Markdown string. The service then queries the LLM a *second* time using `extraction_prompt` to force the AI to return strictly formatted `JSON`. It parses the response using `json.loads(json_str)`, capturing exact indices if the AI hallucinates markdown backticks.

---

## 💾 4. The Relational Memory Framework (Database)

J.A.R.V.I.S uses `PostgreSQL 16`, manipulated via `SQLAlchemy`. The schema is deliberately designed around PostgreSQL’s native `JSONB` support.

### The Standard `profiles` Table
```sql
CREATE TABLE IF NOT EXISTS profiles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    github_url TEXT,
    instagram_url TEXT,
    twitter_url TEXT,
    linkedin_url TEXT,
    description TEXT,              -- Holds the raw 1500+ word AI generated markdown dossier
    additional_info JSONB,         -- Stores arbitrary dictionaries of metadata
    similar_profiles JSONB,        -- Stores highly variable Array payloads
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```
**Why JSONB?**
Instead of creating separate tables for `SocialMediaLinks`, `SimilarProfiles`, and building complex `JOIN` relationships, `JSONB` allows J.A.R.V.I.S to inject dynamic AI payloads as standard dicts. The database natively compresses them, and they can be queried using standard SQL arrows (`profiles.similar_profiles->>0`).

An operational trigger `update_updated_at_column()` hooks into `BEFORE UPDATE ON profiles` to ensure caching logic holds.

---

## 🎨 5. The User Interface Architecture (Next.js)

The frontend is not a static site; it is a highly interactive React application mimicking a high-end HUD (Heads Up Display).

### Component Breakdown
*   **`ChatInterface.tsx` (The Engine Room):** The user enters a string in the bottom input. When `Enter` is pressed, an `Axios` POST is dispatched to FastAPI. While FastAPI blocks for 20-40 seconds processing the AI request, `ChatInterface.tsx` uses interval timeouts to inject "mock" terminal strings into the UI (e.g., `[SYS] Scouring global databanks...`). This keeps the user engaged during the heavy lifting.
*   **`ProfileCard.tsx` (Data Mounting):** Upon receiving the Axios 200 OK response, the raw Markdown from `description` is fed into a `react-markdown` component, which renders the exact bold headings generated by `ai_service.py`. It uses `framer-motion` to stagger the load-in of social media buttons (Twitter, LinkedIn).
*   **`Background.tsx` (Aesthetics):** Uses a complex, layered CSS SVG with `@keyframes` that creates an expanding `#00f3ff` (cyan) radial gradient, providing the visceral feeling of the Arc Reactor.
*   **`ApprovalDialog.tsx`:** Standard `Dialog` modal. Emits the final `POST /api/profiles/` payload once you visually authenticate that the AI didn't hallucinate.

---

## 📦 6. Total Deployment Guide (From Scratch)

Because J.A.R.V.I.S operates on isolated services, setting it up requires specific system tools.

### Phase 1: Bare Metal Requirements
- **Python 3.11+:** To handle `asyncio` and `typing`.
- **Node v18.17+ / npm:** To compile the Next.js React DOM.
- **PostgreSQL 16:** Available via `psql` command line.
- **Ollama:** The daemon must be active. Download from `https://ollama.ai`.

### Phase 2: Core Model Downloading
Open a terminal and force Ollama to download the neural net weights to your local storage:
```bash
ollama pull llama3
```

### Phase 3: PostgreSQL Initialization
We must build the root database manually to accept the application connections.

**Windows CMD:**
```cmd
createdb jarvis
psql -U postgres -d jarvis -f database/init.sql
```

**macOS/Linux Terminal:**
```bash
# If using Homebrew on Mac: brew services start postgresql@16
sudo -u postgres createdb jarvis
sudo -u postgres psql -d jarvis -f database/init.sql
```

### Phase 4: Automated Execution Start
The project provides `start-jarvis.bat` and `start-jarvis.sh`. These shell scripts execute the following dependency injections automatically:
1. `cd backend -> python -m venv venv -> source activate -> pip install -r requirements.txt`.
2. Triggers `uvicorn app.main:app --port 8000 --reload` in the background.
3. `cd frontend -> npm install`.
4. Triggers `npm run dev -- -p 3000` in the foreground.
5. Issues the shell open command to load the browser. 

**Run in Windows:**
```cmd
start-jarvis.bat
```

**Run in UNIX:**
```bash
chmod +x start-jarvis.sh
./start-jarvis.sh
```

---

## 🔌 7. FastAPI Endpoint Complete Listing

For systems integrators looking to plug J.A.R.V.I.S into external applications, the FastAPI layer exposes standard REST paradigms on port `8000`.

| Method | Complete Endpoint URI | Payload / Action | Return Signature |
|--------|-----------------------|------------------|------------------|
| `POST` | `/api/search/` | **Payload:** `{"query": "Target Name"}` <br> Triggers the 4-stage processing pipeline. This is a CPU-intensive, long-polling blocking call. It will not return until Ollama finishes its inference. | A pure JSON object matching `ProfileResponse` minus the ID. |
| `GET`  | `/api/profiles/` | Executes `db.query(Profile).all()` | `List[ProfileResponse]` |
| `GET`  | `/api/profiles/{id}` | Executes `db.query(Profile).filter(Profile.id == id).first()` | Single JSON Profile or HTTP 404 |
| `POST` | `/api/profiles/` | **Payload:** `ProfileCreate` Pydantic Model. Adds object to SQLAlchemy session and calls `db.commit()`. | Database Inserted ID. |
| `DELETE` | `/api/profiles/{id}` | Locates Profile by ID, executes `db.delete(profile)`. | Success message. |
| `GET`  | `/api/profiles/search/{name}` | Fast Lookup. Executes SQL string `ILIKE %name%` to bypass the AI scraper heavily utilizing the index. | Cached Database Profile. |

---

## 🛡️ 8. Known Bottlenecks and Telemetry Handling

J.A.R.V.I.S uses its own highly specific CLI formatting tool called `jarvis_logger.py` to output data.

### Expected Backend CLI Stream Format:
```yaml
============================================================
🔍 NEW SEARCH REQUEST: Linus Torvalds
============================================================
[1/4] 🐙 Querying GitHub central servers for entity: Linus Torvalds...
      ✅ Direct GitHub profile match confirmed.
[2/4] 📱 Scanning global networks for targeted node...
      ✅ LinkedIn profile correlated.
[3/4] 🌐 Infiltrating host and extracting raw data packets: kernel.org...
      ✅ Data packet validation absolute.
[4/4] 🤖 Constructing optimal search matrix and contextual parameters...
      ✅ Model response synthesized.
============================================================
```

### Constraints:
1. **Network Banning (HTTP 429):** The Yahoo SERP bypassing technique inside `scraper_service.py` is robust, but executing 10-15 sequential searches without delay will temporarily trigger IP blocks from Yahoo.
2. **First-Load VRAM Transfer:** Ollama typically halts models when idle to save system memory. The primary search query of any session will experience a lag-time penalty (approx. 6 seconds) while the `llama3.gguf` file is copied from the SSD into the physical GPU/CPU memory spaces.

---

## 📋 9. Strict Licensing Parameters

This project is open-source under the **MIT License**. It was developed strictly for OSINT, portfolio compilation, and development automation.

**CAUTION:** Integrating J.A.R.V.I.S into cron-jobs or high-availability scraping clusters against major corporate endpoints (LinkedIn, Meta, X) violates their public Terms of Service. Development environments are safe, but enterprise production usage requires dedicated residential proxy network routing. 

---

## 👨‍💻 10. Engineering Lead

**Yiğit Erdoğan** - System Architecture, Full-Stack Deployment, Model Tuning.

<br />
<div align="center">
  <p><em>"Sometimes you gotta run before you can walk."</em></p>
</div>