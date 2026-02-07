"""
Shared test fixtures for the ImpulseGuard backend test suite.

Consolidates credential mocking and common setup previously duplicated
across test_api.py and test_e2e.py.
"""

import os
import json
import tempfile
import shutil

import pytest
from unittest.mock import patch, Mock

# ── Create mock service account JSON once at module level ────────────────

_temp_service_account = tempfile.NamedTemporaryFile(
    mode="w", suffix=".json", delete=False
)
_SERVICE_ACCOUNT_DATA = {
    "type": "service_account",
    "project_id": "test-project",
    "private_key_id": "test-key-id",
    "private_key": "-----BEGIN PRIVATE KEY-----\nMOCK_KEY\n-----END PRIVATE KEY-----\n",
    "client_email": "test@test-project.iam.gserviceaccount.com",
    "client_id": "123456789",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": (
        "https://www.googleapis.com/robot/v1/metadata/x509/"
        "test%40test-project.iam.gserviceaccount.com"
    ),
}
json.dump(_SERVICE_ACCOUNT_DATA, _temp_service_account)
_temp_service_account.close()

MOCK_SERVICE_ACCOUNT_PATH = _temp_service_account.name

# Set env var BEFORE any test module imports app
os.environ["VERTEX_SERVICE_ACCOUNT_PATH"] = MOCK_SERVICE_ACCOUNT_PATH

# Patch credentials at module level so app.py / memory.py never hit real GCP
_mock_credentials = Mock()
_mock_credentials.valid = True
_mock_credentials.token = "mock_access_token"

_patcher = patch(
    "google.oauth2.service_account.Credentials.from_service_account_file"
)
_mock_creds_func = _patcher.start()
_mock_creds_func.return_value = _mock_credentials


# ── Shared fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing memory and ChromaDB."""
    memory_dir = tempfile.mkdtemp()
    chroma_dir = tempfile.mkdtemp()
    yield memory_dir, chroma_dir
    shutil.rmtree(memory_dir, ignore_errors=True)
    shutil.rmtree(chroma_dir, ignore_errors=True)


@pytest.fixture
def sample_markdown_files(temp_dirs):
    """Create sample Markdown files in the temp memory directory."""
    memory_dir, _ = temp_dirs

    for filename in ["Goals.md", "Budget.md", "State.md", "Behavior.md"]:
        with open(os.path.join(memory_dir, filename), "w") as f:
            f.write(f"# {filename.replace('.md', '')}\n\nInitial content\n")

    return memory_dir


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Mock environment variables and service account credentials."""
    monkeypatch.setenv("VERTEX_SERVICE_ACCOUNT_PATH", MOCK_SERVICE_ACCOUNT_PATH)

    with patch(
        "google.oauth2.service_account.Credentials.from_service_account_file"
    ) as mock_creds:
        mock_credentials = Mock()
        mock_credentials.valid = True
        mock_credentials.token = "mock_access_token"
        mock_creds.return_value = mock_credentials
        yield
