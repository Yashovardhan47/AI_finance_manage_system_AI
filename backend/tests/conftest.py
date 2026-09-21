import os
from pathlib import Path


TEST_DB = Path(__file__).parent / "test_billflow.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"
os.environ["JWT_SECRET"] = "test-secret-that-is-long-enough-for-tests"
os.environ["ENVIRONMENT"] = "test"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def authenticated_client(client: TestClient):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "demo@example.com",
            "full_name": "Demo User",
            "password": "SecurePass123",
            "monthly_income": 65000,
            "minimum_balance": 10000,
        },
    )
    assert response.status_code == 201
    return client
