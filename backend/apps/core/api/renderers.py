from rest_framework.renderers import JSONRenderer

from .casing import to_camel, transform_keys


class CamelCaseJSONRenderer(JSONRenderer):
    def render(self, data, accepted_media_type=None, renderer_context=None):
        return super().render(transform_keys(data, to_camel), accepted_media_type, renderer_context)
