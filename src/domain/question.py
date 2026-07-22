from pydantic import BaseModel, field_validator


class QuestionRequest(BaseModel):
    question: str
    conversation_id: str | None = None

    @field_validator("question")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("question must not be empty")
        return v.strip()


class StepOut(BaseModel):
    label_en: str
    label_hi: str
    status: str                     # "start" | "done" | "error"
    detail: str | None = None


class ResultTable(BaseModel):
    columns: list[str] = []
    rows: list[list] = []           # ≤200 rows
    row_count: int = 0
    truncated: bool = False


class UsageOut(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class ChartPoint(BaseModel):
    x: str
    y: float | int


class ChartSpec(BaseModel):
    type: str                       # "bar" | "line"
    x: str
    y: str
    points: list[ChartPoint] = []


class AnomalyFlag(BaseModel):
    kind: str
    message: str


class RunDetail(BaseModel):
    run_id: str
    conversation_id: str | None = None
    status: str
    question: str | None = None
    answer: str | None = None
    language: str | None = None
    sql: str | None = None
    steps: list[StepOut] = []
    result: ResultTable | None = None
    caveats: list[str] = []
    followups: list[str] = []
    chart: ChartSpec | None = None
    flags: list[AnomalyFlag] = []
    usage: UsageOut = UsageOut()
    duration_ms: int | None = None
    error: str | None = None
    created_at: str | None = None


class DerivedDatasetRequest(BaseModel):
    run_id: str
    name: str

    @field_validator("name")
    @classmethod
    def _name_ok(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        return v[:80]


class ColumnDescriptionPatch(BaseModel):
    description: str = ""

    @field_validator("description")
    @classmethod
    def _cap(cls, v: str) -> str:
        return v.strip()[:500]


class ConversationSummary(BaseModel):
    id: str
    title: str
    updated_at: str | None = None
    run_count: int = 0


class ConversationDetail(BaseModel):
    id: str
    title: str
    runs: list[RunDetail] = []
