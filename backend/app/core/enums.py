import enum


class RequestStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    REVIEWING = "REVIEWING"
    APPROVED = "APPROVED"
    REVISE = "REVISE"
    BLOCKED = "BLOCKED"
    OVERRIDDEN = "OVERRIDDEN"


class DocumentStatus(str, enum.Enum):
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    READY = "READY"
    PROCESSING_FAILED = "PROCESSING_FAILED"


class AgentType(str, enum.Enum):
    PRODUCT = "PRODUCT"
    BA = "BA"
    ARCHITECTURE = "ARCHITECTURE"
    ENGINEERING = "ENGINEERING"
    QA = "QA"
    SECURITY = "SECURITY"
    USER_EVIDENCE = "USER_EVIDENCE"


class AgentStatus(str, enum.Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    BLOCK = "BLOCK"


class FindingSeverity(str, enum.Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class DeadlineAssessment(str, enum.Enum):
    FEASIBLE = "FEASIBLE"
    DOUBTFUL = "DOUBTFUL"
    INFEASIBLE = "INFEASIBLE"
    UNKNOWN = "UNKNOWN"


class DecisionStatus(str, enum.Enum):
    APPROVED = "APPROVED"
    REVISE = "REVISE"
    BLOCKED = "BLOCKED"


class AuditEventType(str, enum.Enum):
    REQUEST_CREATED = "REQUEST_CREATED"
    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
    DOCUMENT_INDEXED = "DOCUMENT_INDEXED"
    REVIEW_STARTED = "REVIEW_STARTED"
    AGENT_REVIEW_COMPLETED = "AGENT_REVIEW_COMPLETED"
    DECISION_CREATED = "DECISION_CREATED"
    DECISION_ACCEPTED = "DECISION_ACCEPTED"
    REVISION_REQUESTED = "REVISION_REQUESTED"
    DECISION_OVERRIDDEN = "DECISION_OVERRIDDEN"


class EvidenceStatus(str, enum.Enum):
    """Whether a finding's evidence references survived validation."""

    OK = "OK"
    MISSING = "MISSING"


class ReviewRunStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class AgentRunState(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
