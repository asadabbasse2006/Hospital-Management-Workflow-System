
import os

from dotenv import load_dotenv
import pytest

load_dotenv()

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.db.base import Base

# Import models so all tables are registered with Base.metadata.
from app.db import models as core_models  # noqa: F401
from app.db import laboratory_models as lab_models  # noqa: F401


@pytest.fixture(scope="session")
def test_engine():
    database_url = os.getenv("TEST_DATABASE_URL")

    if not database_url:
        pytest.fail(
            "TEST_DATABASE_URL is required. "
            "Set it to a dedicated PostgreSQL test database."
        )

    url = make_url(database_url)
    database_name = (url.database or "").lower()

    if "test" not in database_name:
        pytest.fail(
            "Refusing to run tests: the database name must contain 'test'."
        )

    engine = create_engine(database_url, pool_pre_ping=True)

    try:
        # Safe only because the database name was checked above.
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        yield engine
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def db(test_engine):
    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
    )

    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)