"""Database models. Import new models here so db.create_all() sees them."""

from cms.models.assignment_history import AssignmentHistory
from cms.models.change_request import ChangeRequest, format_cr_number
from cms.models.status_history import StatusHistory
from cms.models.user import User

__all__ = [
    "User",
    "ChangeRequest",
    "StatusHistory",
    "AssignmentHistory",
    "format_cr_number",
]