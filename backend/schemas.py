"""Pydantic schemas: request/response models + Discriminated Union for TestCase content."""
from datetime import datetime
from typing import Annotated, Any, Optional, Union

from pydantic import AliasChoices, BaseModel, Field


# ══════════════════════════════════════════════════════════════════════════
#  Auth
# ══════════════════════════════════════════════════════════════════════════


class UserRegister(BaseModel):
    username: str
    password: str
    email: str = ""


class AdminUserCreate(BaseModel):
    username: str
    password: str = Field(..., min_length=6, max_length=100)
    role: str = "user"
    email: str = ""


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ══════════════════════════════════════════════════════════════════════════
#  AuthConfig
# ══════════════════════════════════════════════════════════════════════════


class AuthConfig(BaseModel):
    enabled: bool = False
    login_url: str = ""
    token_value: str = ""
    login_body: dict[str, Any] = {}
    token_json_path: str = "token"
    header_name: str = "Authorization"
    header_format: str = "Bearer {token}"


# ══════════════════════════════════════════════════════════════════════════
#  Project
# ══════════════════════════════════════════════════════════════════════════


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    url: Optional[str] = ""
    auth_config: Optional[dict] = None
    ai_config: Optional[dict] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    auth_config: Optional[dict] = None
    ai_config: Optional[dict] = None


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    url: Optional[str]
    auth_config: dict = {}
    ai_config: dict = {}
    user_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectDetailResponse(ProjectResponse):
    stats: dict[str, Any] = {}


class ProjectStats(BaseModel):
    test_cases: int = 0
    test_runs: int = 0


# ══════════════════════════════════════════════════════════════════════════
#  TestCase — Discriminated Union content
# ══════════════════════════════════════════════════════════════════════════


class AssertionRule(BaseModel):
    type: str  # status_code / json_path / header / body_contains / element_exists / text_contains / url_contains
    target: str = ""
    operator: str = "eq"  # eq / ne / gt / lt / contains / regex
    expected: Any = None


class APITestCaseContent(BaseModel):
    method: str = "GET"
    url: str = ""
    headers: dict[str, str] = {}
    body: Any = None
    assertions: list[AssertionRule] = []


class UIStep(BaseModel):
    action: str  # click / type / scroll / screenshot / open_app / navigate / wait / keypress
    target: str = ""
    value: str = ""
    screenshot: bool = False
    wait_after: float = 0.5


class UITestCaseContent(BaseModel):
    url: str = ""
    steps: list[UIStep] = []
    assertions: list[AssertionRule] = []


class PerfTestCaseContent(BaseModel):
    url: str = ""
    method: str = "GET"
    concurrency: int = 10
    duration: int = 30
    ramp_up: int = 5


TestCaseContent = Annotated[
    Union[APITestCaseContent, UITestCaseContent, PerfTestCaseContent],
    Field(discriminator="test_type"),
]


class TestCaseCreate(BaseModel):
    name: str
    test_type: str  # api / ui / perf
    source: str = "manual"
    content: dict[str, Any]
    skip_auth: bool = False
    tags: list[str] = []


class TestCaseUpdate(BaseModel):
    name: Optional[str] = None
    test_type: Optional[str] = None
    content: Optional[dict[str, Any]] = None
    skip_auth: Optional[bool] = None
    tags: Optional[list[str]] = None


class TestCaseResponse(BaseModel):
    id: int
    project_id: int
    name: str
    test_type: str
    source: str
    content: dict[str, Any]
    skip_auth: bool = False
    tags: list[str] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TestCaseBatchCreate(BaseModel):
    cases: list[TestCaseCreate]


# ══════════════════════════════════════════════════════════════════════════
#  TestRun
# ══════════════════════════════════════════════════════════════════════════


class TestRunCreate(BaseModel):
    case_ids: list[int]


class TestRunResponse(BaseModel):
    id: int
    project_id: int
    status: str
    result: Optional[str] = None
    summary: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TestRunDetailResponse(TestRunResponse):
    cases: list[TestCaseResponse] = []


# ══════════════════════════════════════════════════════════════════════════
#  TestResult
# ══════════════════════════════════════════════════════════════════════════


class TestResultDetail(BaseModel):
    """Shape of the free-form JSON stored in ``TestResult.detail``.

    New fields are additive — legacy records without them fall back to
    empty strings, keeping the frontend backward-compatible.
    """
    failure_category: str = ""
    failure_message: str = ""
    remediation_hint: str = ""


class TestResultResponse(BaseModel):
    id: int
    run_id: int
    case_id: int
    name: str = ""
    status: str
    detail: Any = {}
    duration_ms: Optional[float] = None
    failure_category: str = ""
    prev_status: Optional[str] = None
    change: str = "new"  # regression / fixed / unchanged / new

    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════════════════════════════════
#  ApiKey
# ══════════════════════════════════════════════════════════════════════════


class ApiKeyCreate(BaseModel):
    name: str = ""
    provider: str
    api_key: str = Field(validation_alias=AliasChoices("api_key", "key"))
    base_url: str = ""
    model: str = ""


class ApiKeyUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None


class ApiKeyResponse(BaseModel):
    id: int
    name: str = ""
    provider: str
    api_key_masked: str
    base_url: str
    model: str = ""
    last_tested_at: Optional[datetime] = None
    is_valid: bool

    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════════════════════════════════
#  Document
# ══════════════════════════════════════════════════════════════════════════


class DocumentResponse(BaseModel):
    id: int
    project_id: int
    filename: str
    doc_type: str
    created_at: datetime
    content_text: Optional[str] = None

    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════════════════════════════════
#  Admin
# ══════════════════════════════════════════════════════════════════════════


class AdminStats(BaseModel):
    users: int = 0
    projects: int = 0
    test_cases: int = 0
    test_runs: int = 0
    api_keys: int = 0
    documents: int = 0


class AdminUserResponse(BaseModel):
    id: int
    username: str
    role: str
    email: str = ""
    verified: bool = False
    ip_address: str = ""
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminUserRoleUpdate(BaseModel):
    role: str


class AdminResetPassword(BaseModel):
    new_password: str = Field(..., min_length=6, max_length=100)


class ChangePassword(BaseModel):
    old_password: str
    new_password: str = Field(..., max_length=100)


class ImportCaseItem(BaseModel):
    name: str
    test_type: str
    source: str = "manual"
    content: dict[str, Any]
    skip_auth: bool = False
    tags: list[str] = []


class ImportRequest(BaseModel):
    cases: list[ImportCaseItem]


class ImportResponse(BaseModel):
    imported: int
    skipped: int
    total: int


class ImportResult(BaseModel):
    imported: int = 0
    failed: int = 0
    errors: list[dict] = []


# ══════════════════════════════════════════════════════════════════════════
#  Pagination
# ══════════════════════════════════════════════════════════════════════════


class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int


# ══════════════════════════════════════════════════════════════════════════
#  Task
# ══════════════════════════════════════════════════════════════════════════


class TaskResponse(BaseModel):
    task_id: str
    status: str
    result: Any = None
    error: Any = None
    created_at: str = ""


# ══════════════════════════════════════════════════════════════════════════
#  AI Planner
# ══════════════════════════════════════════════════════════════════════════


class AIPlanRequest(BaseModel):
    requirement: str
    doc_ids: list[int] = []


class AIPlanResponse(BaseModel):
    cases: list[dict[str, Any]]
    token_usage: dict[str, int]


# ══════════════════════════════════════════════════════════════════════════
#  Token Usage
# ══════════════════════════════════════════════════════════════════════════


class TokenUsageResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    project_id: Optional[int] = None
    provider: str
    model: str
    source: str
    input_tokens: int
    output_tokens: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════════════════════════════════
#  Schedule
# ══════════════════════════════════════════════════════════════════════════


class ScheduleCreate(BaseModel):
    suite_id: int | None = None
    case_ids: list[int] = []
    cron_expr: str
    enabled: bool = True


class ScheduleUpdate(BaseModel):
    suite_id: int | None = None
    case_ids: list[int] | None = None
    cron_expr: str | None = None
    enabled: bool | None = None


class ScheduleResponse(BaseModel):
    id: int
    project_id: int
    suite_id: int | None = None
    case_ids: list[int] = []
    cron_expr: str
    enabled: bool
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class RunByTag(BaseModel):
    tag: str


class DiffItem(BaseModel):
    case_id: int
    case_name: str
    current: str
    previous: Optional[str] = None
    status: str  # new_failure / new_pass / unchanged / new_case


class RunDiffResponse(BaseModel):
    current_run: dict[str, Any]
    previous_run: Optional[dict[str, Any]] = None
    diff: list[DiffItem]
    summary: dict[str, int]


# ══════════════════════════════════════════════════════════════════════════
#  Analytics (PageView)
# ══════════════════════════════════════════════════════════════════════════


class PageViewEnter(BaseModel):
    path: str = Field(validation_alias=AliasChoices("path", "page"))
    referrer: str = ""
    user_agent: str = ""
    session_id: str = ""


class PageViewUpdate(BaseModel):
    duration_ms: int


class PageViewOut(BaseModel):
    id: int
    path: str
    referrer: str = ""
    ip_address: str = ""
    user_agent: str = ""
    session_id: str = ""
    user_id: Optional[int] = None
    duration_ms: int = 0
    entered_at: datetime
    left_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AnalyticsSummary(BaseModel):
    total_views: int = 0
    unique_visitors: int = 0  # unique IPs
    top_pages: list[dict[str, Any]] = []
    recent_views: list[PageViewOut] = []
    views_today: int = 0
    views_7d: list[int] = []  # daily counts for last 7 days


# ══════════════════════════════════════════════════════════════════════════
#  Mock
# ══════════════════════════════════════════════════════════════════════════


class MockConfigResponse(BaseModel):
    id: int
    project_id: int
    enabled: bool
    mode: str
    target_url: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class MockConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    mode: Optional[str] = None
    target_url: Optional[str] = None


class MockRecordResponse(BaseModel):
    id: int
    project_id: int
    enabled: bool
    source: str
    priority: int
    method: str
    path: str
    query_string: str = ""
    request_headers: dict[str, Any] = {}
    request_body: str = ""
    body_type: str = "text"
    response_status: int
    response_headers: dict[str, Any] = {}
    response_body: str = ""
    response_body_type: str = "text"
    content_type: str = ""
    recorded_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    hit_count: int = 0

    model_config = {"from_attributes": True}


class MockRecordUpdate(BaseModel):
    response_status: Optional[int] = None
    response_headers: Optional[dict[str, Any]] = None
    response_body: Optional[str] = None
    response_body_type: Optional[str] = None
    priority: Optional[int] = None
    enabled: Optional[bool] = None


class MockToggleResponse(BaseModel):
    enabled: bool


class MockPaginatedResponse(BaseModel):
    items: list[MockRecordResponse]
    total: int


class MockConvertRequest(BaseModel):
    mock_ids: list[int]


class MockConvertResponse(BaseModel):
    imported: int = 0
    cases: list[dict] = []


# ══════════════════════════════════════════════════════════════════════════
#  Quick Test
# ══════════════════════════════════════════════════════════════════════════


class QuickTestRequest(BaseModel):
    prompt: str
    project_id: int
    context_doc_ids: list[int] = []


class QuickTestResponse(BaseModel):
    task_id: str
    ws_url: str


# ══════════════════════════════════════════════════════════════════════════
#  Schema Driver
# ══════════════════════════════════════════════════════════════════════════


class SchemaParseRequest(BaseModel):
    spec: str = ""
    spec_url: str = ""
    spec_headers: dict[str, str] = {}
    mode: str = "coverage"  # coverage | fuzz | all
    max_fuzz: int = 100


class SchemaEndpointStub(BaseModel):
    name: str
    test_type: str = "api"
    source: str = "schema"
    content: dict[str, Any]
    coverage_key: str = ""


class SchemaParseResponse(BaseModel):
    title: str
    endpoints: list[dict] = []
    stubs: list[SchemaEndpointStub] = []
    spec_title: str = ""
    spec_version: str = ""
    coverage_summary: dict = {}


# ══════════════════════════════════════════════════════════════════════════
#  Project Members
# ══════════════════════════════════════════════════════════════════════════


ROLE_HIERARCHY = {"viewer": 0, "editor": 1, "owner": 2}


class ProjectMemberCreate(BaseModel):
    user_id: int
    role: str = "viewer"


class ProjectMemberUpdate(BaseModel):
    role: str


class ProjectMemberResponse(BaseModel):
    id: int
    project_id: int
    user_id: int
    role: str
    username: str = ""
    created_at: datetime

    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════════════════════════════════
#  p2b: User Center + Admin Panel
# ══════════════════════════════════════════════════════════════════════════


class ProfileUpdate(BaseModel):
    username: str


class PasswordUpdate(BaseModel):
    old_password: str
    new_password: str


class NotificationConfig(BaseModel):
    type: str
    webhook_url: str


class NotificationConfigUpdate(BaseModel):
    type: str
    webhook_url: str


class UserProfileResponse(BaseModel):
    id: int
    username: str
    role: str
    notification_config: dict = {}
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminSystemStats(BaseModel):
    users: int = 0
    projects: int = 0
    test_cases: int = 0
    test_runs: int = 0
    today_executions: int = 0


class AdminProjectItem(BaseModel):
    id: int
    name: str
    user_id: int
    creator_name: str = ""
    member_count: int = 0


class AdminProjectListResponse(BaseModel):
    items: list[AdminProjectItem]
    total: int


# ══════════════════════════════════════════════════════════════════════════
#  p2c: Test Suites
# ══════════════════════════════════════════════════════════════════════════


class SuiteCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    case_ids: list[int] = []


class SuiteUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    case_ids: list[int] | None = None


class SuiteItem(BaseModel):
    id: int
    name: str
    description: str = ""
    case_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class SuiteCaseBrief(BaseModel):
    id: int
    name: str = ""
    url: str = ""

    model_config = {"from_attributes": True}


class SuiteDetail(BaseModel):
    id: int
    name: str
    description: str = ""
    cases: list[SuiteCaseBrief] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class SuiteRunResponse(BaseModel):
    run_id: int
