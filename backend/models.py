from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()


# ── P1a models ─────────────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="user")  # "admin" | "user"
    email = Column(String(120), default="")
    verified = Column(Boolean, default=False)
    ip_address = Column(String(45), default="")
    token_version = Column(Integer, default=0)
    notification_config = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    projects = relationship("Project", back_populates="owner")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    url = Column(String(500), default="")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    auth_config = Column(JSON, default=dict)
    ai_config = Column(JSON, default=dict)
    notification_config = Column(JSON, default=dict)

    owner = relationship("User", back_populates="projects")


# ── P1b models ─────────────────────────────────────────────────────────────


class TestCase(Base):
    __tablename__ = "test_cases"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String(200), nullable=False)
    test_type = Column(String(20), nullable=False)  # api / ui / perf
    source = Column(String(20), default="manual")  # manual / ai_generated
    content = Column(JSON, nullable=False)
    skip_auth = Column(Boolean, default=False)
    tags = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class TestRun(Base):
    __tablename__ = "test_runs"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    status = Column(String(20), default="queued")  # queued/pending/running/done/failed/cancelled/timeout
    result = Column(String(20), nullable=True)  # pass / fail / error
    source = Column(String(20), default="")     # manual / suite / ai_plan
    summary = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TestRunCases(Base):
    __tablename__ = "test_run_cases"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("test_runs.id"), nullable=False)
    case_id = Column(Integer, ForeignKey("test_cases.id"), nullable=False)


class TestResult(Base):
    __tablename__ = "test_results"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("test_runs.id"), nullable=False)
    case_id = Column(Integer, ForeignKey("test_cases.id"), nullable=False)
    status = Column(String(20), nullable=False)  # pass / fail / error
    detail = Column(JSON, default=dict)
    duration_ms = Column(Float, nullable=True)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), default="")
    provider = Column(String(50), nullable=False)
    api_key_encrypted = Column(String(512), nullable=False)
    api_key_masked = Column(String(100), nullable=False)
    base_url = Column(String(500), default="")
    model = Column(String(100), default="")
    last_tested_at = Column(DateTime(timezone=True), nullable=True)
    is_valid = Column(Boolean, default=False)


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    doc_type = Column(String(50), nullable=False)
    file_path = Column(String(500), nullable=False)
    content_text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TokenUsageLog(Base):
    __tablename__ = "token_usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    provider = Column(String(50), nullable=False)
    model = Column(String(100), nullable=False)
    source = Column(String(50), default="ai_plan")
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ── Analytics models ──────────────────────────────────────────────────────


class PageView(Base):
    __tablename__ = "page_views"

    id = Column(Integer, primary_key=True, index=True)
    path = Column(String(500), nullable=False)
    referrer = Column(String(500), default="")
    ip_address = Column(String(45), default="")
    user_agent = Column(String(500), default="")
    session_id = Column(String(64), default="")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    duration_ms = Column(Integer, default=0)
    entered_at = Column(DateTime(timezone=True), server_default=func.now())
    left_at = Column(DateTime(timezone=True), nullable=True)


class Schedule(Base):
    """定时执行：关联测试集或直接指定用例列表。"""
    __tablename__ = "schedules"

    id         = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    suite_id   = Column(Integer, ForeignKey("test_suites.id"), nullable=True)
    case_ids   = Column(JSON, default=list)
    cron_expr  = Column(String(100), nullable=False)
    enabled    = Column(Boolean, default=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ── Mock models ────────────────────────────────────────────────────────────


class MockConfig(Base):
    """Project-level Mock configuration (record/replay mode, target URL)."""

    __tablename__ = "mock_configs"

    id         = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), unique=True, nullable=False)
    enabled    = Column(Boolean, default=False)
    mode       = Column(String(20), default="record")  # record / replay
    target_url = Column(String(500), default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class MockRecord(Base):
    """Single recorded request/response pair."""

    __tablename__ = "mock_records"

    id                = Column(Integer, primary_key=True)
    project_id        = Column(Integer, ForeignKey("projects.id"), nullable=False)
    enabled           = Column(Boolean, default=True)
    source            = Column(String(20), default="auto")    # auto / manual / import
    priority          = Column(Integer, default=0)            # higher = matched first

    # ── Request ──
    method            = Column(String(10), nullable=False)
    path              = Column(String(500), nullable=False)
    query_string      = Column(String(1000), default="")
    request_headers   = Column(JSON, default=dict)
    request_body      = Column(Text, default="")
    body_type         = Column(String(20), default="text")     # text / json / binary

    # ── Response ──
    response_status   = Column(Integer, default=200)
    response_headers  = Column(JSON, default=dict)
    response_body     = Column(Text, default="")
    response_body_type = Column(String(20), default="text")
    content_type      = Column(String(100), default="")

    # ── Metadata ──
    recorded_at       = Column(DateTime(timezone=True), server_default=func.now())
    updated_at        = Column(DateTime(timezone=True), onupdate=func.now())
    hit_count         = Column(Integer, default=0)


# ── Project member permissions ───────────────────────────────────────────


class ProjectMembers(Base):
    """Membership and role assignment for a project."""
    __tablename__ = "project_members"

    id         = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    role       = Column(String(20), default="viewer")  # owner / editor / viewer
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ── p2c: Test Suites ─────────────────────────────────────────────────────


class TestSuite(Base):
    __tablename__ = "test_suites"

    id          = Column(Integer, primary_key=True)
    project_id  = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name        = Column(String(200), nullable=False)
    description = Column(Text, default="")
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class TestSuiteCases(Base):
    __tablename__ = "test_suite_cases"

    id         = Column(Integer, primary_key=True)
    suite_id   = Column(Integer, ForeignKey("test_suites.id"), nullable=False)
    case_id    = Column(Integer, ForeignKey("test_cases.id"), nullable=False)
    sort_order = Column(Integer, default=0)
