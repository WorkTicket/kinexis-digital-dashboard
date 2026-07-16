"""Test bootstrap — ensure config imports succeed without a local .env."""

import os
import tempfile

# Must be set before any app.config import during collection.
os.environ.setdefault(
    "FERNET_KEY",
    "Z2c-kIlhBBD-VDCvqb-1th9QWP_FBf71KX3h02cbmpE=",
)
# Disable local API token middleware in unit tests (desktop token tested separately).
os.environ["KINEAXIS_REQUIRE_API_TOKEN"] = "0"

# Use a temp file DB so tests don't touch the real kinexis.db
_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TEST_DB_PATH = _test_db.name
_test_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"
