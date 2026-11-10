"""
@relation(SDOC-SRS-214, scope=file)
"""

from strictdoc.features.search.facets import SearchFacets, build_facet_query


def test_001_no_facet_builds_no_query() -> None:
    facets = SearchFacets()

    assert facets.is_active() is False
    assert build_facet_query(facets) == ""


def test_002_one_facet_builds_one_condition() -> None:
    assert build_facet_query(SearchFacets(kind="requirement")) == (
        "node.is_requirement"
    )
    assert build_facet_query(SearchFacets(kind="section")) == (
        "node.is_section"
    )
    assert build_facet_query(SearchFacets(status="Active")) == (
        'node["STATUS"] == "Active"'
    )
    assert build_facet_query(SearchFacets(links="with_parent")) == (
        "node.has_parent_requirements"
    )
    assert build_facet_query(SearchFacets(links="without_parent")) == (
        "not node.has_parent_requirements"
    )


def test_003_several_facets_are_joined_with_and() -> None:
    facets = SearchFacets(
        kind="requirement", status="Draft", links="without_parent"
    )

    assert facets.is_active() is True
    assert build_facet_query(facets) == (
        '(node.is_requirement and node["STATUS"] == "Draft"'
        " and not node.has_parent_requirements)"
    )


def test_004_unknown_values_are_ignored() -> None:
    assert build_facet_query(SearchFacets(kind="other", links="other")) == ""
    assert build_facet_query(SearchFacets(status='a"b')) == ""
