import os
from fastapi.testclient import TestClient
import pytest
from pytest_postgresql import factories
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from config import Settings, get_settings
from initialize_db import create_permissions
import models
from main import app
from utils import get_db

postgresql_proc = factories.postgresql_proc()

@pytest.fixture(scope="function")
def test_settings(monkeypatch, postgresql_proc):
    monkeypatch.setenv("POSTGRES_USER", postgresql_proc.user)
    monkeypatch.setenv("POSTGRES_PASSWORD", "")
    monkeypatch.setenv("POSTGRES_DB", postgresql_proc.dbname)
    monkeypatch.setenv("POSTGRES_HOST", postgresql_proc.host)
    monkeypatch.setenv("POSTGRES_PORT", str(postgresql_proc.port))
    
    monkeypatch.setenv("CLIENT_ID", "test-client-id")
    monkeypatch.setenv("CLIENT_SECRET", "test-client-secret")
    
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "")
    monkeypatch.setenv("AWS_ENDPOINT_URL_S3", "")
    monkeypatch.setenv("AWS_REGION", "")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "")
    monkeypatch.setenv("BUCKET_NAME", "test-bucket")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-google-client-secret")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "test.google.redirect.callback.url")

    
    return Settings()

@pytest.fixture(scope="function")
def db(test_settings):
    """Create test database engine"""
    url_san_db = f'postgresql://{test_settings.postgres_user}:@{test_settings.postgres_host}:{test_settings.postgres_port}'
    engine = create_engine(url_san_db, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    with engine.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {test_settings.postgres_db};"))
        conn.execute(text(f"CREATE DATABASE {test_settings.postgres_db};"))
    engine.dispose()
    engine = create_engine(test_settings.database_url, pool_pre_ping=True)
    models.Model.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    create_permissions(session)
        
    yield session
    
    session.rollback()
    session.close()
    models.Model.metadata.drop_all(bind=engine)
    engine.dispose()
    
    cleanup_engine = create_engine(url_san_db, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    with cleanup_engine.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {test_settings.postgres_db};"))
    cleanup_engine.dispose()

@pytest.fixture
def client(db):
    def override_get_db():
        yield db
    
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    
    app.dependency_overrides.clear()