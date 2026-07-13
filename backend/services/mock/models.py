"""MockRecord and MockConfig SQLAlchemy models (1.x declarative style)."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

# NOTE: These models are registered into the global Base via the import
#       in backend/models.py so create_all picks them up.
MockBase = declarative_base()


class MockConfig(MockBase):
    """Project-level Mock configuration (record/replay mode, target URL)."""

    __tablename__ = "mock_configs"

    id         = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), unique=True, nullable=False)
    enabled    = Column(Boolean, default=False)        # master switch
    mode       = Column(String(20), default="record")  # record / replay
    target_url = Column(String(500), default="")       # real service address (record → forward target)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class MockRecord(MockBase):
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
    request_headers   = Column(JSON, default={})
    request_body      = Column(Text, default="")              # JSON text or base64
    body_type         = Column(String(20), default="text")    # text / json / binary

    # ── Response ──
    response_status   = Column(Integer, default=200)
    response_headers  = Column(JSON, default={})
    response_body     = Column(Text, default="")              # JSON text or base64
    response_body_type = Column(String(20), default="text")
    content_type      = Column(String(100), default="")

    # ── Metadata ──
    recorded_at       = Column(DateTime(timezone=True), server_default=func.now())
    updated_at        = Column(DateTime(timezone=True), onupdate=func.now())
    hit_count         = Column(Integer, default=0)            # times replayed
