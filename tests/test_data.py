"""Data integrity, checked against the claims in the written guides.

These exist because data/*.json is regenerated from upstream: if a game patch
(or an upstream parsing change) moves a ratio, this suite is what notices. The
numbers below are the ones asserted in the Suika Box note 20.refiner-recipes.md.
"""

from __future__ import annotations

import pytest

from nms_items import graph
from nms_items.model import SOURCE_SETS, TIER0, Book


@pytest.fixture(scope="module")
def book() -> Book:
    return Book()


def test_recipe_counts(book: Book) -> None:
    """The guide's totals, as of Cosmos 7.06: 361 refining, 1,323 cooking.

    Cosmos added four refiner recipes (357 before), one per new deep-space
    material: Comet Dust, Isotopic Dust (Contaminated Metal until
    Forsaken 7.14), Gelatinous Fibres and Corrupted
    Ichor. Cooking did not change.
    """
    refine = [r for r in book.recipes if r.domain == "refine"]
    cook = [r for r in book.recipes if r.domain == "cook"]
    assert len(refine) == 361
    assert len(cook) == 1323


def test_every_ingredient_resolves(book: Book) -> None:
    for recipe in book.recipes:
        assert recipe.output.id in book.items, recipe.output.id
        for ing in recipe.inputs:
            assert ing.id in book.items, ing.id


def test_amounts_are_positive(book: Book) -> None:
    for recipe in book.recipes:
        assert recipe.output.n > 0
        assert all(ing.n > 0 for ing in recipe.inputs)


def test_machine_matches_input_count(book: Book) -> None:
    expected = {
        1: "Portable / Personal Refiner",
        2: "Medium Refiner",
        3: "Large Refiner",
    }
    for recipe in book.recipes:
        if recipe.domain != "refine":
            continue
        assert recipe.machine == expected[len(recipe.inputs)]


def test_the_three_x6_loops(book: Book) -> None:
    """1 X + 2 Oxygen -> 6 X, for Condensed Carbon, Chlorine, Ionised Cobalt."""
    sixes = {r.output_name for r in book.recipes if r.loop == 6}
    assert sixes == {"Condensed Carbon", "Chlorine", "Ionised Cobalt"}


def test_headline_recipes(book: Book) -> None:
    def find(output: str, inputs: set[str]):
        for recipe in book.recipes:
            if recipe.output_name == output and {
                book.name(i.id) for i in recipe.inputs
            } == inputs:
                return recipe
        raise AssertionError(f"no recipe {inputs} -> {output}")

    assert find("Gold", {"Living Pearl"}).output.n == 100
    assert find("Magnetised Ferrite", {"Platinum", "Oxygen"}).output.n == 10
    assert find("Nanite Cluster", {"Hyaline Brain"}).output.n == 230
    assert find("Nanite Cluster", {"Salvaged Data"}).output.n == 15


def test_tier0_reaches_thirty_materials(book: Book) -> None:
    """The guide's Tier 0 claim: 5 surface substances reach 35 materials total."""
    reached = graph.reachable(book, set(TIER0))
    assert len(reached) == 30
    names = {book.name(i) for i in reached}
    assert {"Chlorine", "Magnetised Ferrite", "Starship Launch Fuel"} <= names
    assert len(reached | set(TIER0)) == 35


def test_asteroids_add_nine(book: Book) -> None:
    tier1 = graph.reachable(book, set(SOURCE_SETS["Tier 1 - + asteroids"]))
    added = tier1 - graph.reachable(book, set(TIER0)) - set(TIER0)
    assert {book.name(i) for i in added} >= {"Nanite Cluster", "Lemmium", "Deuterium"}
    assert len(added) == 9


def test_twentynine_items_cannot_be_refined_into_existence(book: Book) -> None:
    """The guide's must-find list: 29 refiner inputs no refiner recipe makes.

    25 before Cosmos 7.06; its four new materials are only ever inputs.
    """
    refine = [r for r in book.recipes if r.domain == "refine"]
    inputs = {ing.id for r in refine for ing in r.inputs}
    outputs = {r.output.id for r in refine}
    missing = {book.name(i) for i in inputs - outputs}
    assert len(missing) == 29
    assert {"Living Pearl", "Salvaged Data", "Tainted Metal", "Atlantideum"} <= missing
    assert {"Comet Dust", "Isotopic Dust", "Gelatinous Fibres", "Corrupted Ichor"} <= missing


def test_plan_from_tier0(book: Book) -> None:
    plan = graph.plan(book, "LAND3", set(TIER0), 100)  # Magnetised Ferrite
    assert plan.ok
    assert set(plan.raw_totals) <= set(TIER0)
    assert plan.total_seconds > 0


def test_plan_reports_unreachable(book: Book) -> None:
    """Chromatic Metal needs a stellar-metal seed, which Tier 1 does not have."""
    plan = graph.plan(book, "STELLAR2", set(SOURCE_SETS["Tier 1 - + asteroids"]), 30)
    assert not plan.ok


def test_craftable_now(book: Book) -> None:
    have = {"ASTEROID3": 250}  # 250 Platinum
    made = {r.output_name for r, _ in graph.craftable_now(book, have)}
    assert made == {"Nanite Cluster"}
    _, batches = graph.craftable_now(book, have)[0]
    assert batches == 250 // 35
