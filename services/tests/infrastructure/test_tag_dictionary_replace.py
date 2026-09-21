"""Tag dictionary replacement, against a real Mongo in a throwaway database."""

import uuid

import pytest
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from infrastructure.config import settings
from infrastructure.read_repositories.mongo_read_model_materializer import (
    MongoReadModelMaterializer,
)

OTHER_THAN_NER = ("author", "date")


@pytest.fixture
def materializer():
    client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=1000)
    try:
        client.admin.command("ping")
    except PyMongoError:
        pytest.skip("no local Mongo")
    db = client[f"test_tagdict_{uuid.uuid4().hex[:8]}"]
    m = object.__new__(MongoReadModelMaterializer)
    m.artifacts, m.tag_dictionary = db.artifacts, db.tag_dictionary
    db.artifacts.insert_one({"artifact_id": "a1", "workspace_id": "w"})
    yield m
    client.drop_database(db.name)


def _tag(tag: str, entity_type: str) -> dict[str, str]:
    return {"tag": tag, "tag_normalized": tag.lower(), "entity_type": entity_type}


def test_a_rerun_leaves_no_stale_entries_and_keeps_the_authors(materializer):
    """Re-running NER renamed 8d to its registry ID and dropped the deck's only
    accession number (MTT, a false positive). Neither may linger, and the NER
    write must not touch the authors another projection owns."""
    m = materializer
    first = [_tag("8d", "compound_name"), _tag("MTT", "accession_number")]
    m._replace_tags_in_session("a1", first, None, other_entity_types=OTHER_THAN_NER)
    m._replace_tags_in_session("a1", [_tag("Jane Doe", "author")], None)
    rerun = [_tag("CHEMBL6133834", "compound_name")]
    m._replace_tags_in_session("a1", rerun, None, other_entity_types=OTHER_THAN_NER)

    left = {(d["entity_type"], d["tag_normalized"]): d["artifact_count"] for d in m.tag_dictionary.find()}
    assert left == {("compound_name", "chembl6133834"): 1, ("author", "jane doe"): 1}
