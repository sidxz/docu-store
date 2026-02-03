from domain.aggregates.page import Page
from domain.value_objects.compound_mention import CompoundMention


class TestPage:
    def test_create_page(self):
        """Test creating a Page aggregate."""
        page = Page(name="Home")

        assert page.name == "Home"
        assert page.compound_mentions == []
        assert page.id is not None
        assert page.version == 0

    def test_add_compound_mentions(self):
        """Test adding compound_mentions to a page."""
        page = Page(name="Home")
        compound_mentions = [
            CompoundMention(smiles="C1=CC=CC=C1", extracted_name="Benzene"),
            CompoundMention(smiles="CC(=O)O", extracted_name="Acetic Acid"),
        ]

        page.update_compound_mentions(compound_mentions)

        assert len(page.compound_mentions) == 2
        assert page.compound_mentions[0].extracted_name == "Benzene"
        assert page.compound_mentions[1].extracted_name == "Acetic Acid"

    def test_add_compound_mentions_multiple_times(self):
        """Test adding compound_mentions multiple times extends the list."""
        page = Page(name="Home")

        first_batch = [CompoundMention(smiles="C1=CC=CC=C1", extracted_name="Benzene")]
        page.update_compound_mentions(first_batch)

        second_batch = [CompoundMention(smiles="CC(=O)O", extracted_name="Acetic Acid")]
        page.update_compound_mentions(second_batch)

        assert len(page.compound_mentions) == 2

    def test_compound_mentions_added_event(self):
        """Test that CompoundMentionsUpdated event is created."""
        page = Page(name="Home")
        compound_mentions = [CompoundMention(smiles="C1=CC=CC=C1", extracted_name="Benzene")]

        page.update_compound_mentions(compound_mentions)

        events = list(page.collect_events())
        assert len(events) == 2  # Page.Created and CompoundMentionsUpdated
        assert events[1].__class__.__name__ == "CompoundMentionsUpdated"
