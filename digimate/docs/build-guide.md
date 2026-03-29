# Build Guide — Digimate Docker Image

How to build the digimate Docker image and push it to your Nexus Docker registry.

## Prerequisites

- Docker >= 20.10
- Access to your Nexus Docker registry (referred to as `NEXUS_REGISTRY` below — replace with your actual hostname, e.g. `nexus.company.com:8082`)
- Nexus credentials with push permission

## Build

From the `digimate/` project root:

```bash
# Build the image
docker build -t digimate:0.1.0 .

# Also tag as latest
docker tag digimate:0.1.0 digimate:latest
```

Verify it works:

```bash
docker run --rm digimate:0.1.0 --help
```

## Tag for Nexus

```bash
docker tag digimate:0.1.0 NEXUS_REGISTRY/digimate:0.1.0
docker tag digimate:0.1.0 NEXUS_REGISTRY/digimate:latest
```

## Push to Nexus

```bash
# Login (one-time, or when credentials expire)
docker login NEXUS_REGISTRY

# Push both tags
docker push NEXUS_REGISTRY/digimate:0.1.0
docker push NEXUS_REGISTRY/digimate:latest
```

## Verify

Pull the image back from Nexus to confirm:

```bash
docker pull NEXUS_REGISTRY/digimate:0.1.0
docker run --rm NEXUS_REGISTRY/digimate:0.1.0 version
```

## Version Tagging Convention

| Tag | Meaning |
|-----|---------|
| `digimate:0.1.0` | Specific release |
| `digimate:latest` | Most recent stable build |

When releasing a new version:

1. Update `version` in `pyproject.toml` and `__version__` in `src/digimate/__init__.py`
2. Rebuild: `docker build -t digimate:<new-version> .`
3. Tag + push both `:<new-version>` and `:latest`

## CI/CD Automation (Optional)

Example shell script for automated builds:

```bash
#!/bin/bash
set -euo pipefail

VERSION=$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
REGISTRY="${NEXUS_REGISTRY:?Set NEXUS_REGISTRY env var}"

echo "Building digimate:${VERSION}..."
docker build -t "${REGISTRY}/digimate:${VERSION}" -t "${REGISTRY}/digimate:latest" .
docker push "${REGISTRY}/digimate:${VERSION}"
docker push "${REGISTRY}/digimate:latest"
echo "Done — pushed ${REGISTRY}/digimate:${VERSION}"
```
