"""Database models. Import new models here so db.create_all() sees them."""

from cms.models.change_request import ChangeRequest, format_cr_number
from cms.models.user import User

__all__ = ["User", "ChangeRequest", "format_cr_number"]
