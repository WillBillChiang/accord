"""
Accord Application Configuration.

Centralized configuration for the GCP-based Accord Negotiation Engine.
All settings are loaded from environment variables with sensible defaults
for local development.
"""
import os


# GCP Project
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")
GCP_REGION = os.environ.get("GCP_REGION", "us-central1")

# Cloud KMS
KMS_KEY_NAME = os.environ.get(
    "KMS_KEY_NAME",
    f"projects/{GCP_PROJECT_ID}/locations/{GCP_REGION}/keyRings/accord-keyring/cryptoKeys/accord-key",
)

# Firestore
FIRESTORE_DATABASE = os.environ.get("FIRESTORE_DATABASE", "(default)")
SESSIONS_COLLECTION = os.environ.get("SESSIONS_COLLECTION", "sessions")
AUDIT_LOGS_COLLECTION = os.environ.get("AUDIT_LOGS_COLLECTION", "audit_logs")
USERS_COLLECTION = os.environ.get("USERS_COLLECTION", "users")

# Cloud Storage
AUDIT_BUCKET = os.environ.get("AUDIT_BUCKET", "")
DOCUMENTS_BUCKET = os.environ.get("DOCUMENTS_BUCKET", "")

# Firebase Auth
FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", GCP_PROJECT_ID)

# Application
APP_PORT = int(os.environ.get("APP_PORT", "8080"))
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

# LLM Model
MODEL_PATH = os.environ.get("MODEL_PATH", "/app/models/negotiator-7b-q4.gguf")
