from application.dtos.chat_dtos import ContentBlockDTO
from application.dtos.compound_dtos import BioactivityDTO
from infrastructure.chat.nodes.agentic_retrieval import attach_bioactivities_to_molecule_blocks


def test_attaches_bioactivities_by_label():
    blocks = [ContentBlockDTO(type="molecule", smiles="C", label="CMX410")]
    bios = {"cmx410": [BioactivityDTO(assay_type="MIC", value="0.5", unit="uM")]}
    out = attach_bioactivities_to_molecule_blocks(blocks, bios)
    assert out[0].bioactivities and out[0].bioactivities[0].assay_type == "MIC"


def test_no_match_leaves_none():
    blocks = [ContentBlockDTO(type="molecule", smiles="C", label="OTHER")]
    out = attach_bioactivities_to_molecule_blocks(
        blocks, {"cmx410": [BioactivityDTO(assay_type="MIC", value="1")]}
    )
    assert out[0].bioactivities is None
