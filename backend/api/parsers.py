"""Request parsing shared by every endpoint."""

from rest_framework.exceptions import ParseError
from rest_framework.parsers import JSONParser


class ObjectJSONParser(JSONParser):
    """JSON whose top level is an object, as every CharityOS endpoint expects.

    Views read fields with ``request.data.get(...)``; an array, string, number
    or null body used to reach them and fail with a server error.
    """

    def parse(self, stream, media_type=None, parser_context=None):
        data = super().parse(stream, media_type, parser_context)
        if not isinstance(data, dict):
            raise ParseError("The request body must be a JSON object.")
        return data
