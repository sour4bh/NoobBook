FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.15 /uv /uvx /usr/local/bin/

# System dependencies for document processing and browser automation
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    ffmpeg \
    # Playwright Chromium dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Node.js (provides npx for npm-based MCP servers).
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Install Playwright Chromium browser
RUN playwright install chromium

# Copy application code
COPY . .

# Stamp the image with the git SHA for deploy verification.
# Note: This ARG busts the Docker cache from this point onward, ensuring
# the deploy stamp and later layers are re-run. The COPY . . layer above is
# already invalidated naturally whenever source files change.
ARG GIT_SHA=unknown
RUN echo "$GIT_SHA" > /app/.deploy_sha

# Create data directories (will be overlaid by volume mount)
RUN mkdir -p data/projects data/tasks data/temp

# Make entrypoint executable
RUN chmod +x entrypoint.sh

EXPOSE 5001

ENTRYPOINT ["./entrypoint.sh"]
