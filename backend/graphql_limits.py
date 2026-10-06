"""
Limits for incoming GraphQL documents: maximum size, maximum field depth and
no schema introspection (unless GraphiQL is enabled). Violations are answered
with a generic validation error before anything is executed.
"""
from graphql import GraphQLError
from graphql.backend.base import GraphQLDocument
from graphql.backend.core import GraphQLCoreBackend
from graphql.execution import ExecutionResult, execute
from graphql.language import ast
from graphql.language.parser import parse
from graphql.validation import specified_rules, validate
from graphql.validation.rules.base import ValidationRule

MAX_QUERY_LENGTH = 20_000

TOO_LARGE = "Die Anfrage ist zu groß."
TOO_DEEP = "Die Anfrage ist zu tief verschachtelt."
NO_INTROSPECTION = "Introspection ist deaktiviert."


class NoIntrospection(ValidationRule):
    def enter_Field(self, node, *args):
        if node.name.value in ("__schema", "__type"):
            self.context.report_error(GraphQLError(NO_INTROSPECTION, [node]))


def depth_limit(max_depth):
    class DepthLimit(ValidationRule):
        """Rejects operations with more than max_depth nested fields;
        fragments count with the depth of their fields."""

        def __init__(self, context):
            super().__init__(context)
            # a fragment's depth does not depend on where it is spread, so
            # each fragment is measured once (linear in the document size)
            self._fragment_depths = {}

        def enter_OperationDefinition(self, node, *args):
            if self._depth(node.selection_set, frozenset()) > max_depth:
                self.context.report_error(GraphQLError(TOO_DEEP, [node]))

        def _depth(self, selection_set, fragments):
            if selection_set is None:
                return 0
            deepest = 0
            for selection in selection_set.selections:
                if isinstance(selection, ast.Field):
                    depth = 1 + self._depth(selection.selection_set, fragments)
                elif isinstance(selection, ast.FragmentSpread):
                    name = selection.name.value
                    depth = self._fragment_depths.get(name)
                    if depth is None:
                        fragment = self.context.get_fragment(name)
                        # unknown fragments and cycles are reported by other
                        # rules
                        if fragment is None or name in fragments:
                            continue
                        depth = self._depth(fragment.selection_set,
                                            fragments | {name})
                        self._fragment_depths[name] = depth
                else:
                    depth = self._depth(selection.selection_set, fragments)
                deepest = max(deepest, depth)
            return deepest

    return DepthLimit


class LimitedBackend(GraphQLCoreBackend):
    def __init__(self, max_depth, introspection=False):
        super().__init__()
        self.rules = list(specified_rules) + [depth_limit(max_depth)]
        if not introspection:
            self.rules.append(NoIntrospection)

    def document_from_string(self, schema, document_string):
        if len(document_string) > MAX_QUERY_LENGTH:
            raise GraphQLError(TOO_LARGE)
        try:
            document_ast = parse(document_string)
        except RecursionError:
            raise GraphQLError(TOO_DEEP) from None

        def execute_validated(*args, **kwargs):
            errors = validate(schema, document_ast, self.rules)
            if errors:
                return ExecutionResult(errors=errors, invalid=True)
            return execute(schema, document_ast, *args, **kwargs)

        return GraphQLDocument(schema=schema, document_string=document_string,
                               document_ast=document_ast,
                               execute=execute_validated)
