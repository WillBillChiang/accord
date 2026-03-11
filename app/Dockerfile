# Accord Negotiation Engine — GCP Confidential VM Container Image
#
# This image contains the unified negotiation engine: FastAPI server,
# LLM with GPU acceleration (CUDA), protocol engine, agent logic,
# and all GCP integrations. Runs inside a Confidential VM with
# AMD SEV-SNP memory encryption.
#
# Build with CUDA support for NVIDIA L4/H100 GPUs:
#   docker build -t accord-app .
#
# For Artifact Registry:
#   docker build -t ${REGION}-docker.pkg.dev/${PROJECT_ID}/accord/accord-app:${VERSION} .

# Stage 1: Build llama-cpp-python with CUDA
FROM nvidia/cuda:12.4.0-devel-ubuntu22.04 AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3.11-venv \
    python3-pip \
    gcc \
    g++ \
    cmake \
    && rm -rf /var/lib/apt/lists/*

# Build llama-cpp-python with CUDA support
ENV CMAKE_ARGS="-DGGML_CUDA=on"
RUN python3.11 -m pip install --no-cache-dir --prefix=/install \
    llama-cpp-python==0.3.4

# Stage 2: Runtime image
FROM nvidia/cuda:12.4.0-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    python3-pip \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-built llama-cpp-python from builder
COPY --from=builder /install /usr/local

# Install remaining Python dependencies
RUN python3.11 -m pip install --no-cache-dir \
    fastapi>=0.115,\<1.0 \
    'uvicorn[standard]>=0.30,<1.0' \
    google-cloud-kms>=2.21,\<3.0 \
    google-cloud-firestore>=2.16,\<3.0 \
    google-cloud-storage>=2.14,\<3.0 \
    google-cloud-logging>=3.9,\<4.0 \
    firebase-admin>=6.4,\<7.0 \
    pydantic>=2.10,\<3.0 \
    cryptography>=44.0,\<45.0 \
    scipy>=1.14,\<2.0 \
    httpx>=0.27,\<1.0 \
    websockets>=13.0,\<14.0

# Copy application code
COPY . /app/

# Models directory (mount or copy quantized model here)
RUN mkdir -p /app/models

WORKDIR /app

# Run as non-root user
RUN useradd -r -s /bin/false accord
USER accord

EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3.11 -c "import httpx; httpx.get('http://localhost:8080/health').raise_for_status()"

CMD ["python3.11", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
