"""Workflow runtime exception types shared across workflow modules."""


class WorkflowRuntimeError(RuntimeError):
    pass


class ApprovalValidationError(WorkflowRuntimeError):
    """Raised when an approval decision is invalid before mutation."""

    pass


class ApprovalNotFoundError(WorkflowRuntimeError):
    """Raised when an approval queue or frozen approval node cannot be found."""

    pass


class ApprovalConflictError(WorkflowRuntimeError):
    """Raised when an approval exists but is not waiting for a decision."""

    pass
