"""Safe diagnostics: never stringify validation errors or model values."""
import json

from pydantic import ValidationError

from app.providers.base import ProviderError


class ContractViolation(ValueError):
    def __init__(self, path, rule, message):
        self.issue = f'{path}: {rule}'
        super().__init__(message)


class ModelOutputError(ProviderError):
    def __init__(self, code, issues, *, incomplete_reason=None):
        super().__init__(code)
        self.issues = issues
        self.incomplete_reason = incomplete_reason


def incomplete(reason):
    # Upstream text is untrusted, including values that look like enum names.
    reason = reason if isinstance(reason, str) and reason in {'max_output_tokens', 'content_filter'} else 'unknown'
    return ModelOutputError('model_incomplete', [f'response.status: {reason}'], incomplete_reason=reason)


def validation_failure(error, schema):
    if isinstance(error, json.JSONDecodeError):
        return ModelOutputError('model_invalid_json', ['$: invalid json'])
    if isinstance(error, ContractViolation):
        issues = [error.issue]
    elif isinstance(error, ValidationError):
        fields = set(schema.get('properties', {}))
        for definition in schema.get('$defs', {}).values():
            fields.update(definition.get('properties', {}))
        rules = {'missing', 'extra_forbidden', 'string_type', 'string_too_short', 'string_too_long',
                 'int_type', 'int_parsing', 'int_from_float', 'float_type', 'bool_type',
                 'list_type', 'dict_type', 'model_type', 'literal_error', 'greater_than_equal',
                 'less_than_equal', 'too_short', 'too_long', 'string_pattern_mismatch'}
        issues = []
        for item in error.errors(include_url=False, include_context=False, include_input=False)[:8]:
            path = ''
            for part in item['loc'][:8]:
                if isinstance(part, int):
                    path += f'[{part}]'
                else:
                    part = part if part in fields else '<extra>'
                    path += ('.' if path else '') + part
            rule = item['type'] if item['type'] in rules else 'schema violation'
            issues.append(f'{path or "$"}: {rule}')
    else:
        issues = ['$: schema violation']
    return ModelOutputError('model_contract_violation', issues)
