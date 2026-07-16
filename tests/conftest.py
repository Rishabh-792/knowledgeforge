import pytest
from fastapi.testclient import TestClient

from app.api.deps import reset_singletons
from app.core.config import get_settings
from app.core.security import create_access_token
from app.main import create_app


@pytest.fixture(autouse=True)
def fresh_services():
    """Each test gets a clean in-memory store and providers."""
    reset_singletons()
    yield
    reset_singletons()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _auth(role: str, groups: list[str]) -> dict[str, str]:
    token = create_access_token(f"{role}@test", role, groups, get_settings())
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return _auth("admin", ["everyone"])


@pytest.fixture
def curator_headers() -> dict[str, str]:
    return _auth("curator", ["engineering"])


@pytest.fixture
def reader_headers() -> dict[str, str]:
    return _auth("reader", ["engineering"])
