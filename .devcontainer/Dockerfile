FROM python:3.9-slim-bookworm

# Avoid prompts from apt
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    make \
    gcc \
    g++ \
    libpq-dev \
    libgeos-dev \
    libproj-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /workspace

# Python dependencies are managed by uv (see pyproject.toml and uv.lock).
# The virtual environment lives outside the bind-mounted workspace.
COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    PATH=/opt/venv/bin:$PATH

# Shell prompt with git branch and upstream status
COPY bash-prompt.sh /etc/bash-prompt.sh
RUN echo '. /etc/bash-prompt.sh' >> /etc/bash.bashrc
