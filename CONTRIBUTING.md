# Contributing to J.A.R.V.I.S

Thank you for your interest in contributing to J.A.R.V.I.S. This document provides guidelines and instructions for contributing to the repository. Please review it to make the contribution process effective for everyone involved.

---

## Code of Conduct

By participating in this project, you agree to abide by our Code of Conduct. We expect all contributors to maintain a professional, respectful, and inclusive environment. 

---

## How Can I Contribute?

### 1. Reporting Bugs
If you find a bug, please check the [Issue Tracker](../../issues) first to see if it has already been reported. If not, open a new issue and include:
- A clear and descriptive title.
- Steps to reproduce the bug.
- The expected behavior and what actually happened.
- Your operating system, Python version, Node.js/Next.js version, and Ollama version.
- Any relevant logs (from the FastAPI backend or Next.js frontend console).

### 2. Suggesting Enhancements
If you have an idea for a new feature or an improvement, open an issue and include:
- A clear description of the enhancement.
- Why this enhancement would be useful.
- Potential implementation details (if known).

### 3. Submitting Pull Requests (PRs)
Follow these steps to submit your changes:

#### Step 1: Fork and Clone
1. Fork the repository on GitHub.
2. Clone your fork locally:
   ```bash
   git clone https://github.com/YOUR-USERNAME/J.A.R.V.I.S.git
   cd J.A.R.V.I.S
   ```

#### Step 2: Branching
Create a new branch for your feature or bug fix. Use a descriptive naming convention:
```bash
git checkout -b feature/search-enhancement
# OR
git checkout -b fix/yahoo-regex-bypass
```

#### Step 3: Local Development
Ensure you have the full stack running to test your changes. 
*   **Backend:** Python 3.11+, PostgreSQL 16+, FastAPI.
*   **Frontend:** Node.js 18+, Next.js 15.
*   **AI:** Local Ollama instance (default: `llama3`).

If you are modifying scraping logic (`backend/app/services/scraper_service.py`), please ensure you test your regex against multiple target profile structures as social media layouts change frequently.

#### Step 4: Coding Standards
To maintain the quality and readability of the codebase, please adhere to the following standards:
- **Backend (Python):** 
  - Follow PEP 8 style guidelines.
  - Use Python absolute Type Hints (`from typing import Dict, List, Optional`) for all new functions.
  - Use `app.jarvis_logger.logger` instead of standard `print()` statements for terminal output.
- **Frontend (TypeScript/Next.js):** 
  - Use strict TypeScript interfaces.
  - Follow the existing Tailwind CSS class structures for styling. Avoid inline styles where possible.
  - Ensure any new UI components match the established dark-mode aesthetic.

#### Step 5: Commit your Changes
Write clear, concise commit messages. We prefer the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) specification:
```bash
git commit -m "feat(scrapers): added direct support for github organization searches"
git commit -m "fix(ui): resolved flickering issue on the profile card load animation"
```

#### Step 6: Push and Open a PR
1. Push your branch to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```
2. Open a Pull Request from your fork to the `main` branch of the original J.A.R.V.I.S repository.
3. In your PR description, explain what you changed, why you changed it, and link to any relevant issues (e.g., `Closes #12`).

---

## Architectural Context for Contributors

If you are planning major architectural changes, please review the extensive documentation available in the `README.md`. 
As a quick refresher:
- The system heavily relies on parallel web scraping and local LLM inference.
- The PostgreSQL database leverages `JSONB` columns (`additional_info`, `similar_profiles`) rather than strict foreign-key relations to handle flexible LLM outputs. Do not attempt to normalize these without prior discussion.
- The frontend relies on Axios polling during load states to simulate real-time terminal output.

---

## Ethical Scraping Notice

J.A.R.V.I.S is an OSINT tool designed for educational and automated research purposes. When contributing scrapers or modifying request headers, do not submit PRs that attempt to aggressively bypass high-security corporate endpoints using mass-botting techniques (e.g., integrating paid 3rd party CAPTCHA solvers). These changes violate major platforms' Terms of Service and will be rejected. 

---

## Need Help?

If you are stuck on a technical implementation, feel free to open a Discussion on GitHub or reach out to the project lead.

**Engineering Lead:** Yiğit Erdoğan
- LinkedIn: [yiğit-erdoğan-ba7a64294](https://www.linkedin.com/in/yi%C4%9Fit-erdo%C4%9Fan-ba7a64294)
- GitHub: [Yigtwxx](https://github.com/Yigtwxx)
- Reddit: [u/Yigtwx6](https://www.reddit.com/user/Yigtwx6/)
