"""JSON utilities for metaseed."""

import json
from datetime import date, datetime


class DateAwareEncoder(json.JSONEncoder):
    """JSON encoder that handles date and datetime objects.

    Converts date and datetime objects to ISO format strings.
    """

    def default(self, obj):
        """Encode date/datetime objects to ISO format."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        return super().default(obj)
