FROM python:3.12-slim

LABEL maintainer="digimate"
LABEL description="Digimate — lightweight developer agent"

# Avoid Python writing .pyc and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install git (needed by git_ops tools) and clean up
RUN apt-get update && \
    apt-get install -y --no-install-recommends git ripgrep && \
    rm -rf /var/lib/apt/lists/*

# Copy project and install
COPY . /app
RUN pip install --no-cache-dir /app[h2] && \
    rm -rf /app

# Runtime workspace — mount your project here
WORKDIR /workspace

# Persist agent memory and logs across container restarts
VOLUME ["/workspace", "/root/.digimate"]

ENTRYPOINT ["digimate"]
