"""How many papers the answer actually stands on.

Every number here already existed and none of it reached the reader. In the
failure the evaluation recorded, 47 post-2020 papers were retrieved, assembly
kept ten of them all dated 2015-2019, and the answer reported that no post-2020
evidence existed. This strip is what makes that visible.
"""

from __future__ import annotations

from infrastructure.chat.nodes.literature_context_assembly import build_provenance_spec


def test_the_strip_carries_all_three_stages_in_order():
    spec = build_provenance_spec(retrieved=47, assembled=10, cited=0)
    assert spec.panel == "provenance"
    assert spec.categories == ["Returned", "Assembled", "Cited"]
    points = spec.series[0].points
    assert points == [(0.0, 47.0), (1.0, 10.0), (2.0, 0.0)]


def test_a_zero_cited_answer_is_still_drawn():
    # The most important case to render: an answer standing on nothing must not
    # produce an empty chart that looks like no chart.
    spec = build_provenance_spec(retrieved=12, assembled=4, cited=0)
    assert spec.series[0].points[2] == (2.0, 0.0)
