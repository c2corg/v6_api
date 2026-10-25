"""Schema base class, Cornice validator, and the mapping to SQLAlchemy models."""

from cornice.validators import extract_cstruct
from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationError,
    create_model,
    model_validator,
)
from sqlalchemy import inspect

from c2corg_api.models.schema_utils import (
    default_fields_doc,
    default_fields_geometry,
    default_fields_locale,
    split_fields,
)
from c2corg_api.schemas.types import Empty, Map, Str, check_mapping


class Schema(BaseModel):
    """Base class of the request schemas."""

    # unknown fields are ignored, as Colander did; geometries are WKBElements
    model_config = ConfigDict(extra='ignore', arbitrary_types_allowed=True)

    @model_validator(mode='before')
    @classmethod
    def _missing_values(cls, data):
        """Remove the values Colander treats as missing (see `types.Empty`)."""
        data = check_mapping(data)
        result = dict(data)
        for name, field in cls.model_fields.items():
            if name not in data:
                continue
            rules = [m for m in field.metadata if isinstance(m, Empty)]
            is_empty = rules[0].is_empty if rules else (lambda value: value is None)
            if is_empty(data[name]):
                del result[name]
        return result


def validation_errors(error):
    """Return the (name, description) of each error, as Colander named them."""
    return [
        (
            '.'.join(str(part) for part in e['loc']),
            e['msg'] if e['type'] != 'missing' else 'Required',
        )
        for e in error.errors()
    ]


def validate(schema, data):
    """Validate `data` against `schema`; return (validated dict, errors)."""
    try:
        validated = schema.model_validate(data)
    except ValidationError as e:
        return None, validation_errors(e)
    return validated.model_dump(), []


def body_validator(schema):
    """Return a Cornice validator of the JSON body against `schema`."""
    # It replaces `schema=...` with `colander_body_validator` in a view: the
    # validated fields go into `request.validated`, the errors into
    # `request.errors` with the location `body`.

    def validator(request, **kwargs):
        body = extract_cstruct(request)['body']
        if request.errors:
            # not a JSON body: extract_cstruct reported it
            return
        validated, errors = validate(schema, body)
        for name, description in errors:
            request.errors.add('body', name, description)
        if validated is not None:
            request.validated.update(validated)

    return validator


def create_schema(document_schema, associations_schema):
    """Return the schema of a creation: the document with its associations."""
    return create_model(
        f'{document_schema.__name__}Create',
        __base__=document_schema,
        associations=(Map(associations_schema), None),
    )


def update_schema(create):
    """Return the schema of an update: a message and the document."""
    return create_model(
        f'{create.__name__}Update',
        __base__=Schema,
        message=(Str(), ''),
        document=(Map(create), ...),
    )


class ModelSchema:
    """Map a schema to an SQLAlchemy model, like a ColanderAlchemy schema."""

    # `dictify` reads the fields of the schema from a model instance (to
    # serialize it), `objectify` builds a model instance from validated data.
    # `children` gives the ModelSchema of the relationships (locales, geometry).

    def __init__(self, model, schema, children=None, fields=None):
        self.model = model
        self.schema = schema
        self.children = children or {}
        self.fields = list(schema.model_fields) if fields is None else list(fields)

    def dictify(self, obj):
        result = {}
        for name in self.fields:
            if not hasattr(obj, name):
                # e.g. an archive has no locales or geometry relationship
                continue
            value = getattr(obj, name)
            child = self.children.get(name)
            if child is not None and value is not None:
                if isinstance(value, (list, tuple)) or hasattr(value, 'append'):
                    value = [child.dictify(item) for item in value]
                else:
                    value = child.dictify(value)
            result[name] = value
        return result

    def objectify(self, data):
        mapper = inspect(self.model)
        obj = self.model()
        for name, value in data.items():
            if not mapper.has_property(name):
                # not a model attribute (e.g. associations)
                continue
            child = self.children.get(name)
            if child is not None and value is not None:
                if isinstance(value, list):
                    value = [child.objectify(item) for item in value]
                else:
                    value = child.objectify(value)
            setattr(obj, name, value)
        return obj

    def restrict(self, all_fields):
        """Return a copy limited to the given fields, like `restrict_schema`."""
        fields, geom_fields, locale_fields = split_fields(all_fields)
        children = {}
        kept = []
        for name in self.fields:
            if name == 'geometry':
                if geom_fields:
                    kept.append(name)
                    children[name] = self.children[name].only(
                        geom_fields + default_fields_geometry
                    )
            elif name == 'locales':
                kept.append(name)
                children[name] = self.children[name].only(
                    locale_fields + default_fields_locale
                )
            elif name in fields or name in default_fields_doc:
                kept.append(name)
        return ModelSchema(self.model, self.schema, children, kept)

    def only(self, names):
        """Return a copy with only the given fields, in the schema's order."""
        return ModelSchema(
            self.model,
            self.schema,
            self.children,
            [name for name in self.fields if name in names],
        )
