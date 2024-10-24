"""This module creates a specific ESQueryBuilder,
that will be able to handle the full text search correctly
"""

import luqum
from luqum.elasticsearch.tree import EPhrase, EWord
from luqum.elasticsearch.visitor import ElasticsearchQueryBuilder

from ._types import JSONType
from .config import IndexConfig
from .exceptions import FreeWildCardError, QueryAnalysisError

DEFAULT_FIELD_MARKER = "_searchalicious_text"


class FullTextMixin:
    """Implementation of json query transformation to use a query
    on all needed field according to full_text_search configurations
    """

    # attributes provided in implementations
    index_config: IndexConfig
    query_langs: list[str]

    MATCH_TO_MULTI_MATCH_TYPE = {
        "match": "best_fields",
        "match_phrase": "phrase",
    }

    @property
    def full_text_query_fields(self) -> list[str]:
        """List fields to match upon in full text search"""
        fields = []
        lang_fields = set(self.index_config.lang_fields)
        supported_langs = set(self.index_config.supported_langs) & set(self.query_langs)

        for fname, field in self.index_config.full_text_fields.items():
            if fname in lang_fields:
                for lang in supported_langs:
                    subfield_name = f"{field.name}.{lang}"
                    fields.append(subfield_name)
            else:
                fields.append(field.name)
        return fields

    def _transform_query(self, query):
        """Transform the query generated by luqum transformer
        to a query on all necessary fields.
        """
        fields = self.full_text_query_fields
        if "exists" in query:
            raise FreeWildCardError(
                "Free wildcards are not allowed in full text queries"
            )
        if "query_string" in query:
            # no need to transform, just add fields
            query["query_string"]["fields"] = fields
        elif "match" in query or "match_phrase" in query:
            query_type = list(k for k in query.keys() if k.startswith("match"))[0]
            # go for multi_match
            inner_json = query["multi_match"] = query.pop(query_type)
            inner_json.update(inner_json.pop(self.field))
            inner_json["fields"] = fields
            inner_json["type"] = self.MATCH_TO_MULTI_MATCH_TYPE[query_type]
        else:
            raise QueryAnalysisError(
                f"Unexpected query type while analyzing full text query: {query.keys()}"
            )
        return query


class EFullTextWord(EWord, FullTextMixin):
    """Item that may generates a multi_match for word on default field"""

    def __init__(self, index_config: IndexConfig, query_langs=list[str], **kwargs):
        super().__init__(**kwargs)
        self.index_config = index_config
        self.query_langs = query_langs

    @property
    def json(self):
        """Generate the JSON specific to our requests"""
        # let's use the normal way to generate the json
        query = super().json
        # but modify request if we are on default field
        if self.field == DEFAULT_FIELD_MARKER:
            query = self._transform_query(query)
        return query


class EFullTextPhrase(EPhrase, FullTextMixin):
    """Item that generates a multi_match for phrase on default field"""

    def __init__(self, index_config: IndexConfig, query_langs=list[str], **kwargs):
        super().__init__(**kwargs)
        self.index_config = index_config
        self.query_langs = query_langs

    @property
    def json(self):
        """Generate the JSON specific to our requests"""
        # let's use the normal way to generate the json
        query = super().json
        # but modify request depending on the request type
        if self.field == DEFAULT_FIELD_MARKER:
            query = self._transform_query(query)
        return query


class FullTextQueryBuilder(ElasticsearchQueryBuilder):
    """We have our own ESQueryBuilder,
    just to be able to use our FullTextItemFactory,
    instead of the default ElasticSearchItemFactory
    """

    def __init__(self, **kwargs):
        # sanity check, before overriding below
        if "default_field" in kwargs:
            raise NotImplementedError("You should not override default_field")
        super().__init__(
            # we put a specific marker on default_field
            # because we want to be sure we recognize them
            default_field=DEFAULT_FIELD_MARKER,
            **kwargs,
        )

    # fix until https://github.com/jurismarches/luqum/issues/106 is resolved
    def _get_operator_extract(self, binary_operation, delta=8):
        try:
            return super()._get_operator_extract(binary_operation, delta)
        except IndexError:
            return str(binary_operation)

    def visit_word(self, node, context):
        """Specialize the query corresponding to word,
        in the case of full text search
        """
        fields = self._fields(context)
        if fields == [DEFAULT_FIELD_MARKER]:
            # we are in a full text query
            # it's analyzed, don't bother with term
            method = "match_phrase" if self.match_word_as_phrase else "match"
            yield self.es_item_factory.build(
                EFullTextWord,
                q=node.value,
                method=method,
                # we keep fields, we will deal with it in EFullTextWord
                fields=fields,
                _name=self.get_name(node, context),
                index_config=context["index_config"],
                query_langs=context["query_langs"],
            )
        else:
            yield from super().visit_word(node, context)

    def visit_phrase(self, node, context):
        """Specialize the query corresponding to phrase,
        in the case of full text search
        """
        fields = self._fields(context)
        if fields == [DEFAULT_FIELD_MARKER]:
            # we are in a full text query
            # we know it's analyzed, don't bother with term
            yield self.es_item_factory.build(
                EFullTextPhrase,
                phrase=node.value,
                fields=self._fields(context),
                _name=self.get_name(node, context),
                index_config=context["index_config"],
                query_langs=context["query_langs"],
            )
        else:
            yield from super().visit_phrase(node, context)

    def __call__(
        self, tree: luqum.tree.Item, index_config: IndexConfig, query_langs: list[str]
    ) -> JSONType:
        """We add two parameters:

        :param index_config: the index config we are working on
        :param query_langs: the target languages of current query
        """
        self.nesting_checker(tree)
        # we add our parameters to the context
        context = {"index_config": index_config, "query_langs": query_langs}
        elastic_tree = self.visit(tree, context)
        return elastic_tree[0].json