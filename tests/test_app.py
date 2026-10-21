"""A headless pass over the TUI: every binding that changes state."""

from __future__ import annotations

import asyncio
import json

import pytest

from nms_items import graph
from nms_items.app import SORTS, RecipeApp
from nms_items.inventory import Inventory
from nms_items.model import Book


@pytest.fixture(scope="module")
def book() -> Book:
    return Book()


def run(coro):
    return asyncio.run(coro)


def test_app_flows(book: Book, tmp_path_factory) -> None:
    inv_path = tmp_path_factory.mktemp("state") / "inventory.json"

    async def scenario() -> None:
        app = RecipeApp(book)
        app.inv = Inventory(inv_path)
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            main = app.screen
            table = main.query_one("#table")
            # Every refining recipe, however many the current patch has: the count
            # itself is pinned by test_data.test_recipe_counts, not by the UI.
            assert table.row_count == len(book.search(domain="refine"))  # the default domain

            # search debounces, so give the timer a chance
            await pilot.press("slash")
            for char in "platinum":
                await pilot.press(char)
            await pilot.pause(0.3)
            await pilot.pause(0.3)
            assert 0 < table.row_count < len(book.search(domain="refine"))
            assert all("platinum" in r.search_key for r in main.rows)

            await pilot.press("enter")  # back to the table
            await pilot.press("s")      # sort
            await pilot.press("f")      # domain
            await pilot.pause()
            assert main.domain == "cook"
            await pilot.press("f")
            await pilot.press("f")
            await pilot.pause()
            assert main.domain == "refine"

            # reverse lookup and back
            await pilot.press("r")
            await pilot.pause()
            assert main.item_role == "input"
            await pilot.press("backspace")
            await pilot.pause()
            assert main.item_filter is None

            # chain screen
            await pilot.press("c")
            await pilot.pause(0.2)
            assert app.screen.__class__.__name__ == "ChainScreen"
            await pilot.press("t")
            await pilot.press("k")
            await pilot.pause(0.2)
            await pilot.press("escape")
            await pilot.pause(0.2)

            # inventory round trip, including persistence
            await pilot.press("i")
            await pilot.pause(0.2)
            assert app.screen.__class__.__name__ == "InventoryScreen"
            await pilot.press("slash")   # insert mode, as everywhere else
            await pilot.pause(0.2)
            for char in "platinum 250":
                await pilot.press(char)
            await pilot.press("enter")
            await pilot.pause(0.3)
            assert app.inv.items == {"ASTEROID3": 250}
            assert app.screen.query_one("#can-table").row_count == 1
            await pilot.press("escape")
            await pilot.pause(0.2)

            await pilot.press("question_mark")
            await pilot.pause(0.2)
            assert app.screen.__class__.__name__ == "HelpScreen"
            await pilot.press("escape")
            await pilot.pause(0.2)

    run(scenario())
    assert json.loads(inv_path.read_text()) == {"ASTEROID3": 250}


def test_bindings_do_not_leak_between_screens(book: Book, tmp_path) -> None:
    """`s` sorts the recipe list, but only while the recipe list is on top."""

    async def scenario() -> None:
        app = RecipeApp(book)
        app.inv = Inventory(tmp_path / "inv.json")
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            main = app.screen
            before = main.sort_index

            await pilot.press("e")  # cooking effects
            await pilot.pause(0.3)
            assert app.screen is not main
            await pilot.press("s")
            await pilot.pause(0.2)
            assert main.sort_index == before

            await pilot.press("escape")
            await pilot.pause(0.2)
            await pilot.press("s")
            await pilot.pause(0.2)
            assert main.sort_index != before

    run(scenario())


def test_nanite_and_food_screens(book: Book, tmp_path) -> None:
    async def scenario() -> None:
        app = RecipeApp(book)
        app.inv = Inventory(tmp_path / "inv.json")
        async with app.run_test(size=(150, 40)) as pilot:
            await pilot.pause()

            await pilot.press("n")
            await pilot.pause(0.3)
            nanites = app.screen
            assert nanites.__class__.__name__ == "NaniteScreen"
            assert nanites.query_one("#nanite-table").row_count == len(graph.nanite_ladder(book))
            await pilot.press("s")  # the screen's own sort, not the list's
            await pilot.pause(0.2)
            assert nanites.sort_index == 1
            await pilot.press("escape")
            await pilot.pause(0.2)

            await pilot.press("e")
            await pilot.pause(0.3)
            foods = app.screen
            assert foods.__class__.__name__ == "FoodScreen"
            assert foods.query_one("#effect-table").row_count == 19
            assert foods.query_one("#dish-table").row_count > 0
            await pilot.press("escape")
            await pilot.pause(0.2)

            await pilot.press("m")
            await pilot.pause(0.4)
            tools = app.screen
            assert tools.__class__.__name__ == "MultiToolScreen"
            assert tools.query_one("#type-table").row_count == 8
            assert tools.query_one("#weapon-table").row_count == 7
            tabs = tools.query_one("#mt-tabs")
            assert tabs.active == "tab-types"
            # Brackets must work even with a wide DataTable focused, which
            # would otherwise swallow the arrow keys for scrolling.
            tools.query_one("#type-table").focus()
            await pilot.pause(0.2)
            await pilot.press("]")
            await pilot.pause(0.3)
            assert tabs.active == "tab-weapons"
            await pilot.press("[")
            await pilot.pause(0.3)
            assert tabs.active == "tab-types"

    run(scenario())


def test_vim_motions(book: Book, tmp_path) -> None:
    """j/k/gg/G/ctrl+d move the cursor; the search box is insert mode."""

    async def scenario() -> None:
        app = RecipeApp(book)
        app.inv = Inventory(tmp_path / "inv.json")
        async with app.run_test(size=(150, 30)) as pilot:
            await pilot.pause()
            main = app.screen
            table = main.query_one("#table")

            for _ in range(3):
                await pilot.press("j")
            await pilot.pause(0.2)
            assert table.cursor_row == 3
            await pilot.press("k")
            await pilot.pause(0.2)
            assert table.cursor_row == 2

            await pilot.press("G")
            await pilot.pause(0.3)
            assert table.cursor_row == table.row_count - 1

            # A lone g does nothing; gg goes to the top.
            await pilot.press("g")
            await pilot.pause(0.1)
            assert table.cursor_row == table.row_count - 1
            await pilot.press("g")
            await pilot.pause(0.3)
            assert table.cursor_row == 0

            await pilot.press("ctrl+d")
            await pilot.pause(0.2)
            assert table.cursor_row > 0

            # Insert mode: letters are text, not commands.
            await pilot.press("slash")
            await pilot.pause(0.2)
            assert app.focused.id == "search"
            for char in "cobalt":
                await pilot.press(char)
            await pilot.pause(0.3)
            await pilot.pause(0.3)
            assert main.query_text == "cobalt"
            assert main.sort_index == 0  # the s in "cobalt" did not sort

            # Escape leaves insert mode and keeps the filter...
            await pilot.press("escape")
            await pilot.pause(0.3)
            assert app.focused.id == "table"
            assert main.query_text == "cobalt"

            # ...and a second Escape, in normal mode, clears it.
            await pilot.press("escape")
            await pilot.pause(0.3)
            assert main.query_text == ""
            assert table.row_count == len(book.search(domain="refine"))

    run(scenario())


def test_help_scrolls_instead_of_closing(book: Book, tmp_path) -> None:
    async def scenario() -> None:
        app = RecipeApp(book)
        app.inv = Inventory(tmp_path / "inv.json")
        async with app.run_test(size=(150, 30)) as pilot:
            await pilot.pause()
            await pilot.press("question_mark")
            await pilot.pause(0.3)
            box = app.screen.query_one("#help-box")

            for _ in range(5):
                await pilot.press("j")
            await pilot.pause(0.3)
            assert app.screen.__class__.__name__ == "HelpScreen"
            assert box.scroll_offset.y > 0

            await pilot.press("q")
            await pilot.pause(0.3)
            assert app.screen.__class__.__name__ == "RecipeScreen"

    run(scenario())


def test_cooking_toggle_survives_vim_keys(book: Book, tmp_path) -> None:
    """k is cursor-up now, so the cooking toggle had to move to C."""

    async def scenario() -> None:
        app = RecipeApp(book)
        app.inv = Inventory(tmp_path / "inv.json")
        async with app.run_test(size=(150, 30)) as pilot:
            await pilot.pause()
            await pilot.press("i")
            await pilot.pause(0.3)
            inventory = app.screen
            assert inventory.with_cooking is True

            inventory.query_one("#inv-table").focus()
            await pilot.press("k")  # cursor-up, not a toggle
            await pilot.pause(0.2)
            assert inventory.with_cooking is True

            await pilot.press("C")
            await pilot.pause(0.3)
            assert inventory.with_cooking is False

    run(scenario())


def test_portal_screen(book: Book, tmp_path) -> None:
    """Convert, search, copy and save -- all through the one input box."""
    from nms_items.portals import LocationBook

    async def scenario() -> None:
        app = RecipeApp(book)
        app.inv = Inventory(tmp_path / "inv.json")
        # A scratch file: the test must not append to the committed one.
        app.locations = LocationBook.load()
        app.locations.path = tmp_path / "locations.json"
        saved_at_start = len(app.locations)

        async with app.run_test(size=(150, 40)) as pilot:
            await pilot.pause()
            await pilot.press("P")
            await pilot.pause(0.4)
            screen = app.screen
            assert screen.__class__.__name__ == "PortalScreen"
            assert screen.query_one("#loc-table").row_count == saved_at_start

            # A pasted portal code converts.
            await pilot.press("slash")
            for char in "40E907FF0D6B":
                await pilot.press(char)
            await pilot.pause(0.3)
            assert screen.current.galactic == "056A:0086:07EF:00E9"

            # p cycles the planet glyph, which is the one a galactic
            # address cannot carry.
            await pilot.press("enter")  # back to the table
            await pilot.press("p")
            await pilot.pause(0.2)
            assert screen.current.portal_code == "50E907FF0D6B"

            # Anything that is not an address searches instead.
            screen.query_one("#portal-input").value = ""
            await pilot.pause(0.2)
            screen.query_one("#portal-input").value = "royal"
            await pilot.pause(0.3)
            assert screen.current is None
            assert 0 < screen.query_one("#loc-table").row_count < saved_at_start
            assert all("royal" in loc.search_key for loc in screen.rows)

            # f narrows to a kind, o to where it came from; independently.
            screen.query_one("#portal-input").value = ""
            await pilot.pause(0.3)
            await pilot.press("f")
            await pilot.pause(0.2)
            assert screen.kind == "multi-tool"
            assert all(loc.kind == "multi-tool" for loc in screen.rows)

            await pilot.press("o")
            await pilot.pause(0.2)
            assert screen.origin == "mine"
            assert screen.rows == []  # nothing shipped was found here
            await pilot.press("o")
            await pilot.pause(0.2)
            assert screen.origin == "shared"
            assert all(loc.kind == "multi-tool" for loc in screen.rows)
            await pilot.press("o")
            await pilot.pause(0.2)
            assert screen.origin is None

            # Enter on a saved row loads it into the converter.
            screen.query_one("#loc-table").focus()
            await pilot.press("enter")
            await pilot.pause(0.2)
            assert screen.current is not None
            assert screen.current.portal_code == screen.rows[0].code

            # s saves whatever is converted, through the modal.
            await pilot.press("s")
            await pilot.pause(0.3)
            assert app.screen.__class__.__name__ == "LocationModal"
            for char in "Test System":
                await pilot.press(char)
            await pilot.press("enter")
            await pilot.pause(0.3)
            assert len(app.locations) == saved_at_start + 1
            saved = app.locations.locations[-1]
            assert saved.name == "Test System"
            # The modal defaults to your own find, and dates it.
            assert saved.origin == "mine"
            assert saved.added

            # d drops the highlighted one again.
            await pilot.press("G")
            await pilot.pause(0.2)
            await pilot.press("d")
            await pilot.pause(0.3)
            assert len(app.locations) == saved_at_start

    run(scenario())


def test_glyph_picker_dials_an_address(book: Book, tmp_path) -> None:
    """D builds a code from the symbols: keys, the cursor, and undo."""

    async def scenario() -> None:
        app = RecipeApp(book)
        app.inv = Inventory(tmp_path / "inv.json")
        async with app.run_test(size=(150, 40)) as pilot:
            await pilot.pause()
            await pilot.press("P")
            await pilot.pause(0.4)
            screen = app.screen
            await pilot.press("D")
            await pilot.pause(0.3)
            picker = app.screen
            assert picker.__class__.__name__ == "GlyphPickerModal"

            # A typed digit picks that glyph; a stray one comes off again.
            for char in "63FFD968046":
                await pilot.press(char)
            await pilot.press("9", "backspace")
            assert picker.code == "63FFD968046"
            # Undo puts the cursor back on the last glyph kept: boat, and
            # one right of boat is bug.
            await pilot.press("l", "enter")
            assert picker.code == "63FFD9680467"
            # Full: more digits are ignored, Enter hands the code over.
            await pilot.press("A", "enter")
            await pilot.pause(0.3)
            assert app.screen is screen
            assert screen.current.portal_code == "63FFD9680467"

            # Escape leaves the converter as it was.
            await pilot.press("D")
            await pilot.pause(0.3)
            await pilot.press("1", "escape")
            await pilot.pause(0.3)
            assert screen.current.portal_code == "63FFD9680467"

    run(scenario())


def test_portal_screen_drops_the_list_when_narrow(book: Book, tmp_path) -> None:
    async def scenario() -> None:
        app = RecipeApp(book)
        app.inv = Inventory(tmp_path / "inv.json")
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.pause()
            await pilot.press("P")
            await pilot.pause(0.4)
            assert app.screen.query_one("#portal-right").display is False

    run(scenario())


def test_multitool_screen_reaches_the_addresses(book: Book, tmp_path) -> None:
    """The shortlist in guide 21 is multi-tools, so m -> P lands filtered."""

    async def scenario() -> None:
        app = RecipeApp(book)
        app.inv = Inventory(tmp_path / "inv.json")
        async with app.run_test(size=(150, 40)) as pilot:
            await pilot.pause()
            await pilot.press("m")
            await pilot.pause(0.4)
            await pilot.press("P")
            await pilot.pause(0.4)
            assert app.screen.__class__.__name__ == "PortalScreen"
            assert app.screen.kind == "multi-tool"

    run(scenario())


def _titles(screen) -> list[str]:
    return [command.title for command in screen.palette_commands()]


def test_palette_lists_every_mode_and_marks_the_current_one(book, tmp_path) -> None:
    """Ctrl+P is the way to reach a mode without cycling to it blind."""

    async def scenario() -> None:
        app = RecipeApp(book)
        app.inv = Inventory(tmp_path / "inv.json")
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            main = app.screen
            commands = list(main.palette_commands())

            # Every domain and every sort is offered by name, not by cycle.
            assert [c.title for c in commands if c.title.startswith("Recipes:")] == [
                "Recipes: Refining", "Recipes: Cooking", "Recipes: All recipes",
            ]
            assert len([c for c in commands if c.title.startswith("Sort:")]) == 6

            # Exactly one of each group is marked as where you are.
            for group in ("Recipes:", "Sort:"):
                on = [c for c in commands if c.title.startswith(group) and c.current]
                assert len(on) == 1, group
            assert "● " in [c for c in commands if c.current][0].display

            # Running one sets that mode outright rather than stepping to it.
            by_title = {c.title: c for c in commands}
            by_title["Sort: units profit"].run()
            await pilot.pause(0.2)
            assert SORTS[main.sort_index][0] == "profit"
            by_title["Recipes: All recipes"].run()
            await pilot.pause(0.2)
            assert main.domain is None

            # And the marks follow.
            now = {c.title: c.current for c in main.palette_commands()}
            assert now["Sort: units profit"] and not now["Sort: multiplier"]

            # Plain actions carry no mode mark.
            assert by_title["Nanite ladder"].current is None
            assert by_title["Nanite ladder"].display.startswith("  ")

    run(scenario())


def test_every_screen_with_modes_offers_them(book, tmp_path) -> None:
    """A screen that has a cycle key must also have palette entries for it."""

    async def scenario() -> None:
        app = RecipeApp(book)
        app.inv = Inventory(tmp_path / "inv.json")
        async with app.run_test(size=(150, 40)) as pilot:
            await pilot.pause()

            for key, expect in (
                ("c", ("Source: Tier 0 - any planet", "Quantity")),
                ("n", ("Sort: nanites/hour", "Sort: how gettable")),
                ("m", ("Tab: types", "Tab: tips")),
                ("i", ("Recipes: refining only", "Clear inventory")),
                ("P", ("Kind: everything", "Found: my finds")),
            ):
                await pilot.press(key)
                await pilot.pause(0.4)
                screen = app.screen
                assert screen.COMMANDS, screen.__class__.__name__
                titles = _titles(screen)
                for wanted in expect:
                    assert wanted in titles, (screen.__class__.__name__, titles)
                # Every mode group has exactly one current entry.
                groups: dict[str, int] = {}
                for command in screen.palette_commands():
                    if command.current:
                        groups[command.title.split(":")[0]] = (
                            groups.get(command.title.split(":")[0], 0) + 1
                        )
                assert all(n == 1 for n in groups.values()), groups
                # Twice: on the inventory screen the first Escape only leaves
                # the add field, the way it does in vim.
                await pilot.press("escape")
                await pilot.pause(0.2)
                await pilot.press("escape")
                await pilot.pause(0.3)
                assert app.screen.__class__.__name__ == "RecipeScreen"

    run(scenario())


def test_portal_palette_offers_the_address_actions_only_when_there_is_one(
    book, tmp_path
) -> None:
    async def scenario() -> None:
        app = RecipeApp(book)
        app.inv = Inventory(tmp_path / "inv.json")
        async with app.run_test(size=(150, 40)) as pilot:
            await pilot.pause()
            await pilot.press("P")
            await pilot.pause(0.4)
            screen = app.screen
            assert "Copy portal code" not in _titles(screen)

            await pilot.press("slash")
            for char in "40E907FF0D6B":
                await pilot.press(char)
            await pilot.pause(0.3)
            titles = _titles(screen)
            assert "Copy portal code" in titles
            assert "Save this address" in titles

            # The help line on a copy command is the thing it will copy.
            copy = next(
                c for c in screen.palette_commands() if c.title == "Copy portal code"
            )
            assert copy.help == "40E907FF0D6B"

    run(scenario())


def test_dropping_an_address_is_undoable(book: Book, tmp_path) -> None:
    """The mistake this exists for: d, then realising, then u."""
    from nms_items.portals import LocationBook

    async def scenario() -> None:
        app = RecipeApp(book)
        app.inv = Inventory(tmp_path / "inv.json")
        app.locations = LocationBook.load()
        app.locations.path = tmp_path / "locations.json"
        total = len(app.locations)

        async with app.run_test(size=(150, 40)) as pilot:
            await pilot.pause()
            await pilot.press("P")
            await pilot.pause(0.4)
            screen = app.screen
            first = screen.rows[0].name

            await pilot.press("d")
            await pilot.pause(0.3)
            assert len(app.locations) == total - 1
            assert [loc.name for loc in app.locations.trash] == [first]
            assert first not in [loc.name for loc in screen.rows]

            # T shows the trash, and the row is in it.
            await pilot.press("T")
            await pilot.pause(0.3)
            assert screen.showing_trash
            assert [loc.name for loc in screen.rows] == [first]

            # u from inside the trash puts the highlighted one back.
            await pilot.press("u")
            await pilot.pause(0.3)
            assert len(app.locations) == total
            assert app.locations.trash == []
            # back where it was, not appended
            assert app.locations.locations[0].name == first

            await pilot.press("T")
            await pilot.pause(0.3)
            assert not screen.showing_trash
            assert screen.rows[0].name == first

    run(scenario())


def test_undo_works_from_the_list_too(book: Book, tmp_path) -> None:
    from nms_items.portals import LocationBook

    async def scenario() -> None:
        app = RecipeApp(book)
        app.inv = Inventory(tmp_path / "inv.json")
        app.locations = LocationBook.load()
        app.locations.path = tmp_path / "locations.json"
        total = len(app.locations)

        async with app.run_test(size=(150, 40)) as pilot:
            await pilot.pause()
            await pilot.press("P")
            await pilot.pause(0.4)
            screen = app.screen

            await pilot.press("d")
            await pilot.press("d")
            await pilot.pause(0.4)
            assert len(app.locations.trash) == 2
            second = app.locations.trash[-1].name

            # u without opening the trash undoes the last drop.
            await pilot.press("u")
            await pilot.pause(0.3)
            assert len(app.locations) == total - 1
            assert app.locations.locations[0].name == second

            # The palette offers it by name, and says which one.
            undo = next(
                c for c in screen.palette_commands() if c.title == "Undo the last drop"
            )
            assert undo.help == app.locations.trash[-1].name
            undo.run()
            await pilot.pause(0.3)
            assert len(app.locations) == total
            assert app.locations.trash == []

            # With an empty trash the palette stops offering it.
            assert "Undo the last drop" not in [
                c.title for c in screen.palette_commands()
            ]

    run(scenario())


def test_the_save_form_refuses_rather_than_quietly_correcting(book, tmp_path) -> None:
    """A bad kind used to become "other" and a bad galaxy became Euclid."""
    from nms_items.portals import LocationBook

    async def scenario() -> None:
        app = RecipeApp(book)
        app.inv = Inventory(tmp_path / "inv.json")
        app.locations = LocationBook.load()
        app.locations.path = tmp_path / "locations.json"
        total = len(app.locations)

        async with app.run_test(size=(150, 40)) as pilot:
            await pilot.pause()
            await pilot.press("P")
            await pilot.pause(0.4)
            await pilot.press("slash")
            for char in "40E907FF0D6B":
                await pilot.press(char)
            await pilot.pause(0.3)
            await pilot.press("enter")
            await pilot.press("s")
            await pilot.pause(0.4)
            modal = app.screen
            assert modal.__class__.__name__ == "LocationModal"

            def field(selector):
                return modal.query_one(selector)

            def error():
                return modal.problem

            # No name: refused, and the cursor goes where the problem is.
            field("#loc-name").value = ""
            await pilot.press("enter")
            await pilot.pause(0.3)
            assert app.screen is modal
            assert "needs a name" in error()
            assert modal.focused.id == "loc-name"

            # A kind that is not a kind: refused, and it says which are.
            field("#loc-name").value = "Test System"
            field("#loc-kind").value = "starfighter"
            await pilot.press("enter")
            await pilot.pause(0.3)
            assert app.screen is modal
            assert "multi-tool" in error()
            assert modal.focused.id == "loc-kind"

            # A galaxy that is not a galaxy: refused, with the range.
            field("#loc-kind").value = "multi"      # a prefix is fine
            field("#loc-galaxy").value = "999"
            await pilot.press("enter")
            await pilot.pause(0.3)
            assert app.screen is modal
            assert "1 to 256" in error()
            assert modal.focused.id == "loc-galaxy"

            # Fixed: it saves, and the prefix resolved to the full kind.
            field("#loc-galaxy").value = "10"
            await pilot.press("enter")
            await pilot.pause(0.4)
            assert app.screen is not modal
            assert len(app.locations) == total + 1
            saved = app.locations.locations[-1]
            assert saved.kind == "multi-tool"
            assert saved.galaxy == 10
            assert saved.name == "Test System"

    run(scenario())


def test_storage_screen(book: Book, tmp_path) -> None:
    """`w` answers for the highlighted output, then for anything typed."""

    async def scenario() -> None:
        app = RecipeApp(book)
        app.inv = Inventory(tmp_path / "inv.json")
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            main = app.screen
            output = main.current_recipe().output_name
            assert "Store" in str(main.query_one("#detail").render())

            await pilot.press("w")
            await pilot.pause(0.3)
            storage = app.screen
            assert storage.__class__.__name__ == "StorageScreen"
            assert storage.rows[0][0].name == output

            await pilot.press("slash")
            search = storage.query_one("#store-search")
            search.value = ""
            for char in "gravitino":
                await pilot.press(char)
            await pilot.pause(0.3)
            item, placement = storage.rows[0]
            assert item.name == "Gravitino Ball"
            assert placement.action == "sell"
            assert "Sell" in str(storage.query_one("#store-detail").render())

            await pilot.press("escape")  # out of the search box
            await pilot.press("escape")  # off the screen
            await pilot.pause(0.2)
            assert app.screen is main

    run(scenario())


def test_theme_choice_persists_and_transparency(book: Book, tmp_path, monkeypatch) -> None:
    """The choice is saved, and the transparent theme turns on the ANSI
    colour that keeps the terminal's background showing through.
    """
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    from nms_items import themes

    async def scenario() -> None:
        app = RecipeApp(book)
        app.inv = Inventory(tmp_path / "inv.json")
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            assert app.theme == themes.DEFAULT_THEME
            assert app.ansi_color is True
            app.theme = "dracula-neutral"
            await pilot.pause()
            assert app.ansi_color is None

    run(scenario())
    assert themes.load_theme() == "dracula-neutral"


@pytest.mark.parametrize(
    "key",
    ["", "i", "w", "n", "e", "m", "P"],
    ids=["recipes", "inventory", "storage", "nanites", "effects", "multitools", "portals"],
)
def test_every_theme_paints_every_screen(
    book: Book, tmp_path, monkeypatch, key: str
) -> None:
    """The stylesheet is all theme variables; a missing one fails at load."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    async def scenario() -> None:
        app = RecipeApp(book)
        app.inv = Inventory(tmp_path / "inv.json")
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            if key:
                await pilot.press(key)
                await pilot.pause(0.2)
            for name in app.available_themes:
                app.theme = name
                await pilot.pause()

    run(scenario())
