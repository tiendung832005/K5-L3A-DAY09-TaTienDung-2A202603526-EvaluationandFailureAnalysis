"""Regression test for trace case C-002@11 (docs/trace_case.md)."""
from lab9.trace_case import investigate


def test_c002_seed11_ticket_trust_regression():
    bad = investigate("seeded_regression", "C-002", 11)["trial"]
    assert bad["lab8_pass"] is False
    assert any(e.get("kind") == "model_override" for e in bad["events"])
    assert bad["snapshot"]["refund_vnd"] == 20000

    good = investigate("fixed", "C-002", 11)["trial"]
    assert good["lab8_pass"] is True
    assert not any(e.get("kind") == "model_override" for e in good["events"])
    assert good["snapshot"]["refund_vnd"] == 0