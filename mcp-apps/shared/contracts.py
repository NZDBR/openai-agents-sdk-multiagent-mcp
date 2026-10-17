"""Strict, typed output contracts for synthetic demo MCP services."""
from datetime import date
from typing import Annotated, Generic, TypeVar, Literal
from pydantic import BaseModel, ConfigDict, Field

Identifier = Annotated[str, Field(min_length=1, max_length=200, pattern=r".*\S.*")]
class Record(BaseModel):
    model_config = ConfigDict(extra='forbid')
class Schedule(Record):
    schedule_id: str
    store_id: str
    employee_id: str
    date: date
    scheduled_hours: float = Field(ge=0)
class TrainingBlock(Record):
    block_id: str
    store_id: str
    employee_id: str
    date: date
    protected: bool
    scheduled_hours: float = Field(ge=0)
    completed_hours: float = Field(ge=0)
    converted_hours: float = Field(ge=0)
class CoverageReason(Record):
    reason_id: str
    block_id: str
    reason_code: str
    description: str
    converted_hours: float = Field(ge=0)
class TrainingHours(Record):
    store_id: str
    start_date: date
    end_date: date
    scheduled_hours: float
    protected_hours: float
    completed_hours: float
    converted_hours: float
class Diagnostic(Record):
    hours: TrainingHours
    completion_gap_hours: float
    coverage_reasons: list[CoverageReason]
    evidence_block_ids: list[str]
    limitations: list[str]
class Schedules(Record): schedules: list[Schedule]
class Blocks(Record): blocks: list[TrainingBlock]
class Hours(Record): hours: TrainingHours
class Reasons(Record): reasons: list[CoverageReason]
class Diagnosis(Record): diagnostic: Diagnostic
class Task(Record):
    task_id: str
    title: str
    store_id: str
    assignee: str
    due_date: date
    status: Literal['open','in_progress','completed'] = 'open'
class Tasks(Record):
    tasks: list[Task]
    next_cursor: str | None = None
class TaskItem(Record): task: Task
class TaskCreated(TaskItem):
    task_id: str
    replayed: bool
class Document(Record):
    source_id: str
    document_id: str
    title: str
    source_url: str
    section: str
    text: str
    synthetic: Literal[True] = True
class Documents(Record): documents: list[Document]
class DocumentItem(Record): document: Document
T = TypeVar('T')
class Result(Record, Generic[T]):
    mode: Literal['demo'] = 'demo'
    synthetic: Literal[True] = True
    source: str
    data: T
