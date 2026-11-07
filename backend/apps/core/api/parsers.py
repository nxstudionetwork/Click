from rest_framework.parsers import JSONParser

from .casing import to_snake, transform_keys


class CamelCaseJSONParser(JSONParser):
    def parse(self, stream, media_type=None, parser_context=None):
        return transform_keys(super().parse(stream, media_type, parser_context), to_snake)
