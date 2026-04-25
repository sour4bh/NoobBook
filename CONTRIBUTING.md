# Contributing to NoobBook

Thanks for your interest in contributing to NoobBook!

## Repository and Branch

- Canonical repository: [`sour4bh/NoobBook`](https://github.com/sour4bh/NoobBook).
- Default branch: `main`.
- All pull requests target `main`.

> Historical note: an earlier `develop` branch and the `TeacherOp/NoobBook` upstream fork are legacy. Do not clone or target them for new work.

---

## Development Setup

NoobBook requires **Supabase** (PostgreSQL + Storage + Auth). The app will not start without it.

### Prerequisites

| Requirement | Install |
|-------------|---------|
| **Python 3.10+** | `brew install python3` (macOS) / `sudo apt install python3 python3-venv` (Ubuntu) |
| **Node.js 18+** | `brew install node` (macOS) / [nodesource](https://github.com/nodesource/distributions) (Ubuntu) |
| **Docker & Docker Compose** | [docs.docker.com/get-docker](https://docs.docker.com/get-docker/) |
| **LibreOffice** (optional) | `brew install libreoffice` / `sudo apt install libreoffice` — for DOCX/PPTX processing |
| **FFmpeg** (optional) | `brew install ffmpeg` / `sudo apt install ffmpeg` — for audio processing |

### API Keys You'll Need

Get these before starting:

| Key | Where to get it | Required? |
|-----|-----------------|-----------|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/) | Yes |
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com/) | Yes |
| `PINECONE_API_KEY` + `PINECONE_INDEX_NAME` | [pinecone.io](https://www.pinecone.io/) | Yes |
| `ELEVENLABS_API_KEY` | [elevenlabs.io](https://elevenlabs.io/) | No — audio features |
| `TAVILY_API_KEY` | [tavily.com](https://tavily.com/) | No — web search fallback |
| `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` | [Google Cloud Console](https://console.cloud.google.com/) | No — Google Drive import |

### Option A: Docker Setup (Recommended)

This starts everything — Supabase, backend, frontend, and runs database migrations automatically.

```bash
# 1. Clone
git clone https://github.com/sour4bh/NoobBook.git
cd NoobBook

# 2. Copy env template and add your API keys
cp docker/.env.example docker/.env
nano docker/.env    # Add ANTHROPIC_API_KEY, OPENAI_API_KEY, PINECONE_API_KEY, PINECONE_INDEX_NAME

# 3. Run setup (generates Supabase secrets, starts everything)
bash docker/setup.sh

# 4. Open NoobBook
open http://localhost
```

**Manage Docker setup:**
```bash
bash docker/stop.sh           # Stop all services (data preserved)
bash docker/setup.sh          # Re-run setup (idempotent, safe to re-run)
bash docker/reset.sh          # Stop all services
bash docker/reset.sh -v       # Stop + delete ALL data (destructive)
```

| Service | URL |
|---------|-----|
| NoobBook | `http://localhost` |
| Backend API | `http://localhost/api/v1` (proxied via nginx) |
| Supabase Studio | `http://localhost:8000` |

**Supabase Studio login:** The setup script auto-generates the dashboard password. To find it:
```bash
grep DASHBOARD docker/supabase/.env
```
Default username is `supabase`.

### Option B: Local Development (Without Docker for the App)

You still need Supabase running. Either use Docker for just Supabase, or connect to a Supabase Cloud instance.

**Step 1: Start Supabase (pick one)**

```bash
# Option: Self-hosted Supabase via Docker
cp docker/supabase/.env.example docker/supabase/.env
# Edit docker/supabase/.env with generated secrets (see backend/supabase/SETUP.md)
docker network create noobbook-network
docker compose -f docker/supabase/docker-compose.yml --env-file docker/supabase/.env up -d

# Option: Supabase Cloud
# Get keys from https://app.supabase.com/project/_/settings/api
```

**Step 2: Run database migrations**

```bash
# Via psql (self-hosted)
psql -h localhost -p 5432 -U postgres -d postgres -f backend/supabase/init.sql

# Or via Supabase Studio: open http://localhost:8000 → SQL Editor → paste init.sql → Run
```

**Step 3: Configure environment**

```bash
cp backend/.env.template backend/.env
nano backend/.env
```

Fill in your API keys AND the Supabase keys:
```bash
# Required API keys
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
PINECONE_API_KEY=...
PINECONE_INDEX_NAME=...

# Required Supabase keys (app won't start without these)
SUPABASE_URL=http://localhost:8000          # Or your Supabase Cloud URL
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-role-key
```

**Step 4: Install and run**

```bash
# macOS / Linux
bin/setup                     # Creates venv, installs all dependencies
bin/dev                       # Starts backend (:5001) + frontend (:5173)

# Windows
cd backend && python -m venv venv && venv\Scripts\activate && pip install -r requirements.txt
cd ..\frontend && npm install
cd ..
python start.py               # Starts both servers (run from repo root)
python stop.py                # Stops both servers
```

**Step 5: Install Playwright (for web scraping)**
```bash
npx playwright install
```

For the full self-hosted Supabase guide, see [`backend/supabase/SETUP.md`](backend/supabase/SETUP.md).

---

## How to Contribute

1. **Fork the repository**

2. **Sync with `main`**
   ```bash
   git checkout main
   git pull origin main
   ```

3. **Create your feature branch**
   ```bash
   git checkout -b your-feature-name
   ```

4. **Make your changes**
   - See `CLAUDE.md` for code guidelines
   - Follow existing patterns in the codebase

5. **Run tests**
   ```bash
   cd backend && pytest
   ```

6. **Push and open a Pull Request against `main`**
   ```bash
   git push origin your-feature-name
   ```
   Open the PR against `sour4bh/NoobBook`'s `main` branch.

## Important

- All PRs target `main` on `sour4bh/NoobBook`
- Keep PRs focused on a single feature or fix
- See `CLAUDE.md` for code style, design system, and architecture details

## Project Structure

Read [`STRUCTURE.md`](STRUCTURE.md) before adding new files. It is the current repo-root structure guide and carries the placement checklist reviewers apply to every new file.

The project is migrating from a mechanism-first backend layout to a domain-first layout. During the migration the following paths are **legacy/migration sources**, not preferred homes for new work, and must not receive new files:

- `backend/app/services/` (new files should land under a domain subtree, not directly here)
- `backend/app/utils/`
- `backend/app/services/ai_agents/`
- `backend/app/services/ai_services/`
- `backend/app/services/tool_executors/`
- `backend/app/services/tools/`
- `backend/app/services/studio_services/jobs/`
- `backend/app/services/studio_services/studio_processing/`
- `backend/data/prompts/`
- `frontend/src/components/hooks/` (directory removed by `NBB-602`; entry retained for the `NBB-103` legacy-files guardrail until `NBB-706` retires it)

Older guidance in `AGENTS.md`, `CLAUDE.md`, and `REFACTORING.md` that describes those bucket names as current or preferred architecture is superseded by `STRUCTURE.md` until the migration completes.

Agents working on structural migration tickets (`docs/tickets/`): see [`docs/tickets/REFACTORY_SETUP.md`](docs/tickets/REFACTORY_SETUP.md) for refactory plugin setup and the move-plan workflow.

## Questions?

Open an issue or reach out at [noob@noobbooklm.com](mailto:noob@noobbooklm.com)
