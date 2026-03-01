<div align="center">
  <h1>J.A.R.V.I.S</h1>
  <p><strong>Just A Rather Very Intelligent System</strong></p>
  <p><em>Comprehensive AI-Powered OSINT & Profile Analysis Architecture</em></p>

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

<br />

---

## 1. Project Overview & Philosophy

J.A.R.V.I.S is a modular, full-stack Open Source Intelligence (OSINT) and profile analysis system. It automates the process of manual internet research by taking a single query (a person's name) and orchestrating parallel scraping, indexing, and synthesis tasks. 

By unifying web scraping, API querying, and local Large Language Models (LLMs), J.A.R.V.I.S pulls raw unstructured data across the web—from developer platforms like GitHub to visually intensive platforms like Instagram and professional networks like LinkedIn. The final output is a completely structured, extensive JSON dossier formatted as an intelligence report.

The core philosophy of J.A.R.V.I.S relies on data privacy and local execution. All AI analysis is handled completely on your local machine using **Ollama**. Queries, scraped contents, and results never leave your localized network architecture until persisted into your private PostgreSQL database.

---

## 2. Core Architecture & Stack Breakdown

J.A.R.V.I.S utilizes a decoupled frontend-backend architecture integrated with a relational SQL memory layer.

### 2.1 Backend Core (Python / FastAPI)
- **FastAPI:** Chosen for its asynchronous nature (`async/await`) allowing parallel I/O bound operations (like simultaneous Wikipedia, GitHub, and Yahoo requests) and native Pydantic validation.
- **BeautifulSoup4 / Requests:** Powers the web extractors and scrapers. Handles HTTP communication and DOM parsing.
- **SQLAlchemy:** The native Object Relational Mapper (ORM) that manages database session pooling and maps PostgreSQL schemas to Python classes.
- **Ollama Python Client:** Bridges the FastAPI async loop and the local LLM daemon running on the host machine.

### 2.2 Frontend Core (Next.js / TypeScript)
- **Next.js 15 App Router:** Provides server-side rendering boundaries and nested layouts.
- **Tailwind CSS:** Utility-first styling enabling the dark-mode exclusive visual identity.
- **Framer Motion:** Handles physics-based animations for loading components, modal mounts, and staggered list rendering in profile cards.
- **React Hooks & Axios:** Custom hooks manage the extensive polling and search state machine (Idle -> Fetching Data -> AI Analysis -> Formatting -> Display/Save).

### 2.3 Persistence Unit (PostgreSQL 16)
- PostgreSQL is utilized specifically for its native support of the `JSONB` data type. Because the LLM outputs varied lengths of arrays (like "Similar Profiles") and deep nested structures, standard SQL normalization would require excessive joined tables. `JSONB` allows J.A.R.V.I.S to store structured, semi-schemaless LLM data while retaining SQL indexing and search capabilities.

---

## 3. The 4-Stage Processing Pipeline

When a user initiates a search request, J.A.R.V.I.S transitions through four specific pipeline stages managed by distinct backend services.

### Stage 1: The Developer Index (`github_service.py`)
Because many targets are software engineers, GitHub is the first point of contact. The service utilizes the `https://api.github.com` endpoints.
1. **Direct Lookup:** It attempts an exact username query corresponding to the given string.
2. **Fuzzy Fallback:** If a 404 is encountered, the system queries `/search/users?q={name}&per_page=1`. It parses the exact login ID from the highest confidence text match.
3. **Repository Interrogation:** Once a valid user is found, a secondary call to `/users/{username}/repos` pulls down the user's top 5 repositories sorted by their most recent `updated` timestamp.
4. **Context Formatting:** The raw JSON is converted into a strictly formatted plaintext string injected directly into the LLM context.

### Stage 2: The Social Bypass Extractor (`scraper_service.py`)
Scraping LinkedIn, Instagram, or X (Twitter) directly via `requests` typically results in immediate HTTP 403 blocks. To circumvent corporate scraping limits, this service uses search-engine proxying.
1. **Yahoo Subspace:** The system routes queries (e.g., `"{name} linkedin"`) through Yahoo Search.
2. **DOM Parsing:** `BeautifulSoup4` extracts every anchor (`<a>`) tag from the search engine result page.
3. **URL Unpacking:** Yahoo obfuscates true URLs behind redirect strings (e.g., `/RU=https...`). J.A.R.V.I.S decodes these payloads using Python's `urllib.parse.unquote`.
4. **Regex Execution:** The decoded URLs are passed through strict Regular Expressions. For Instagram, it matches `r'instagram\.com/([a-zA-Z0-9._]+)'` but applies a negative filter to prevent capturing tags `['p', 'reel', 'explore']`. This ensures only the base profile URL is stored.

### Stage 3: The Deep Packet Infiltrator (`search_service.py`)
This service extracts the actual biographical text required to write a dossier.
1. **Visual Authentication Constraint:** It queries the Wikipedia API (`en.wikipedia.org/w/api.php`) with the target name. To stop name collisions, it converts both strings to lowercase arrays (`query_words_norm.issubset(title_words_norm)`) and removes Unicode accents (`unicodedata.normalize`). Only if the set perfectly overlaps does it pull a profile thumbnail.
2. **Multi-Vector Scraping:** The script creates 5 distinct search queries (Name + Biography, Name + Education, etc.). It grabs 5 URLs per query, deduplicating them.
3. **Deep Document Parsing:** It targets the top 4 URLs (explicitly avoiding social media sites). It downloads the raw DOM and executes `element.decompose()` recursively on all `<script>`, `<style>`, `<header>`, and `<nav>` tags. 
4. **Sanitization:** It extracts purely the `<p>`, `<h1>` and semantic text, strips white spaces, truncates it to the first 8,000 dense characters, and returns the text blob.

### Stage 4: Local AI Synthesis (`ai_service.py`)
All formatted data from Stages 1-3 is compacted into a single prompt.
1. **The System Prompt:** The local AI (Ollama Llama 3 or Qwen) is given a highly restrictive identity. It is commanded to write paragraphs analyzing motives, a psychological profile, controversies, influence networks, and future trajectories.
2. **Hallucination Prevention:** The prompt explicitly instructs: *"You MUST ONLY write about the exact requested person. If the search context is about a CLEARLY DIFFERENT person, you MUST IGNORE that context entirely."* 
3. **JSON Structuring Protocol:** Once the raw dossier is generated, `ai_service.py` executes a second lightweight AI pass requesting the summary to be strictly formatted into a clean `{ "name": "", "description": "", "similar_profiles": [] }` payload for frontend ingestion.

---

## 4. Database Schema Deep Dive

The PostgreSQL 16 `profiles` table is defined as follows to optimize for both structure and flexibility:

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| `id` | `SERIAL` | `PRIMARY KEY` | Unique autoincrementing record identifier. |
| `name` | `VARCHAR(255)` | `NOT NULL`, `INDEXED` | The search target name, optimized via B-Tree index for rapidly retrieving past searches. |
| `github_url` | `TEXT` | `NULL` | Extracted verified developer profile. |
| `instagram_url` | `TEXT` | `NULL` | Formatted IG Handle. |
| `twitter_url` | `TEXT` | `NULL` | Formatted X Handle. |
| `linkedin_url` | `TEXT` | `NULL` | Formatted Professional Handle. |
| `description` | `TEXT` | `NULL` | The full 1,500+ word AI generated dossier. |
| `additional_info` | `JSONB` | `NULL` | Stores dynamic nested objects (raw metrics). |
| `similar_profiles`| `JSONB` | `NULL` | Array of text strings containing equivalent nodes. |
| `created_at` | `TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP` | Initial save time. |
| `updated_at` | `TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP` | Auto-updates on edit via `update_updated_at_column()` PL/pgSQL database trigger. |

---

## 5. User Interface Architecture

The Next.js frontend is fully componentized.

1. **`ChatInterface.tsx`:** The core input terminal. When a user submits a string, it establishes an `Axios` POST to the FastAPI backend. While FastAPI blocks processing the AI request, `ChatInterface.tsx` uses interval timeouts to inject mock terminal strings into the UI to indicate backend progress.
2. **`Background.tsx`:** An absolutely positioned, CSS-animated SVG layer that pulses to provide an Arc Reactor aesthetic.
3. **`ProfileCard.tsx`:** Upon receiving the Axios 200 OK response, this component mounts. It parses the Markdown generated by the AI and displays the social links via customized `lucide-react` SVGs.
4. **`ApprovalDialog.tsx`:** To prevent filling the database with hallucinated profiles, the system implements a holding state. The user must manually click "Save" to trigger the `POST /api/profiles/` commit protocol.

---

## 6. Deployment Guide

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
*Modify `backend/app/config.py` if you wish to swap instances (e.g., `qwen2.5:14b`).*

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
The project provides `start-jarvis.bat` and `start-jarvis.sh`. These shell scripts execute the dependency injections automatically:
1. Triggers `python -m venv venv` and `pip install -r requirements.txt`.
2. Triggers `uvicorn app.main:app --port 8000 --reload` in the background.
3. Triggers `npm install`.
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

## 7. FastAPI Endpoint Mapping

The `routes/` directory manages all external HTTP interfacing.

| Method | Complete Endpoint URI | Payload / Action | Return Signature |
|--------|-----------------------|------------------|------------------|
| `POST` | `/api/search/` | **Payload:** `{"query": "Target Name"}` <br> Triggers the 4-stage processing pipeline. This is a CPU-intensive, long-polling blocking call. It will not return until Ollama finishes its inference. | A pure JSON object matching `ProfileResponse` minus the ID. |
| `GET`  | `/api/profiles/` | Executes `db.query(Profile).all()` | `List[ProfileResponse]` |
| `GET`  | `/api/profiles/{id}` | Executes `db.query(Profile).filter(Profile.id == id).first()` | Single JSON Profile or HTTP 404 |
| `POST` | `/api/profiles/` | **Payload:** `ProfileCreate` Pydantic Model. Adds object to SQLAlchemy session and calls `db.commit()`. | Database Inserted ID. |
| `DELETE` | `/api/profiles/{id}` | Locates Profile by ID, executes `db.delete(profile)`. | Success message. |
| `GET`  | `/api/profiles/search/{name}` | Fast Lookup. Executes SQL string `ILIKE %name%` to bypass the AI scraper heavily utilizing the index. | Cached Database Profile. |

---

## 8. Known Bottlenecks and Constraints

1. **Scraper Flagging:** Repeated requests (`scraper_service.py`) against Yahoo SERPs in short intervals will temporarily IP-ban your network. Setting `time.sleep()` parameters in the python thread is recommended if you intend to run batch queries.
2. **First-Load VRAM Transfer:** Ollama typically halts models when idle to save system memory. The primary search query of any session will experience a lag-time penalty while the model file is copied from the SSD into the physical GPU/CPU memory spaces.

---

## 9. Licensing Parameters

This project is open-source under the **MIT License**. It was developed strictly for OSINT, portfolio compilation, and development automation.

System operators are fully responsible for ensuring their usage of automated scraping scripts complies with all target platforms' `robots.txt` specifications and Terms of Service constraints.

---

## 10. Engineering Lead

**Yiğit Erdoğan** - System Architecture, Full-Stack Deployment, Model Tuning.

- 💼 **LinkedIn:** [yiğit-erdoğan-ba7a64294](https://www.linkedin.com/in/yi%C4%9Fit-erdo%C4%9Fan-ba7a64294)
- 🤖 **Reddit:** [u/Yigtwx6](https://www.reddit.com/user/Yigtwx6/)
- 🐙 **GitHub:** [Yigtwxx](https://github.com/Yigtwxx)