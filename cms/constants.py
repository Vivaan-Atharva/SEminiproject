"""Fixed values used across the application.

Keep these in one place so the models, forms, services and templates all agree.
"""


class Role:
    REQUESTER = "Requester"
    REVIEWER = "Reviewer"
    ENGINEER = "Engineer"
    ADMIN = "Admin"

    ALL = [REQUESTER, REVIEWER, ENGINEER, ADMIN]


class Status:
    SUBMITTED = "Submitted"
    UNDER_REVIEW = "Under Review"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    ASSIGNED = "Assigned"
    IN_PROGRESS = "In Progress"
    RESOLVED = "Resolved"
    CLOSED = "Closed"
    REOPENED = "Reopened"

    ALL = [
        SUBMITTED,
        UNDER_REVIEW,
        APPROVED,
        REJECTED,
        ASSIGNED,
        IN_PROGRESS,
        RESOLVED,
        CLOSED,
        REOPENED,
    ]
    # A change request in one of these statuses is finished.
    TERMINAL = [REJECTED, CLOSED]
    # A change request in one of these statuses can no longer be overdue.
    NOT_DUE = [RESOLVED, CLOSED, REJECTED]
    # Statuses in which an engineer is expected to be working on the request.
    ENGINEER_WORK = [ASSIGNED, IN_PROGRESS, REOPENED]
    # Statuses waiting for a reviewer.
    AWAITING_REVIEW = [SUBMITTED, UNDER_REVIEW]


class Priority:
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"

    ALL = [CRITICAL, HIGH, MEDIUM, LOW]


class CRType:
    BUG_FIX = "Bug fix"
    ENHANCEMENT = "Enhancement"
    CONFIGURATION = "Configuration change"
    OTHER = "Other"

    ALL = [BUG_FIX, ENHANCEMENT, CONFIGURATION, OTHER]


# Parts of the product a change request can affect.
COMPONENTS = [
    "Web application",
    "Mobile application",
    "Backend API",
    "Database",
    "Infrastructure",
    "Documentation",
]
