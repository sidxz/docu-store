from domain.aggregates.page import Page
from domain.value_objects.compound import Compound


class TestPage:
    def test_create_page(self):
        """Test creating a Page aggregate."""
        page = Page(name="Home")

        assert page.name == "Home"
        assert page.compounds == []
        assert page.id is not None
        assert page.version == 0

    def test_add_compounds(self):
        """Test adding compounds to a page."""
        page = Page(name="Home")
        compounds = [
            Compound(smiles="C1=CC=CC=C1", extracted_name="Benzene"),
            Compound(smiles="CC(=O)O", extracted_name="Acetic Acid"),
        ]

        page.add_compounds(compounds)

        assert len(page.compounds) == 2
        assert page.compounds[0].extracted_name == "Benzene"
        assert page.compounds[1].extracted_name == "Acetic Acid"

    def test_add_compounds_multiple_times(self):
        """Test adding compounds multiple times extends the list."""
        page = Page(name="Home")

        first_batch = [Compound(smiles="C1=CC=CC=C1", extracted_name="Benzene")]
        page.add_compounds(first_batch)

        second_batch = [Compound(smiles="CC(=O)O", extracted_name="Acetic Acid")]
        page.add_compounds(second_batch)

        assert len(page.compounds) == 2

    def test_compounds_added_event(self):
        """Test that CompoundsAdded event is created."""
        page = Page(name="Home")
        compounds = [Compound(smiles="C1=CC=CC=C1", extracted_name="Benzene")]

        page.add_compounds(compounds)

        events = list(page.collect_events())
        assert len(events) == 2  # Page.Created and CompoundsAdded
        assert events[1].__class__.__name__ == "CompoundsAdded"
