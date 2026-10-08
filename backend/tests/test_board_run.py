import uuid

from app.scripts import board_run
from app.scripts.board_run import cited_documents, jaccard, pairwise_title_overlap, summarize

DOC = str(uuid.uuid4())


def test_jaccard_of_disjoint_and_identical_sets():
    assert jaccard(frozenset({"a"}), frozenset({"b"})) == 0.0
    assert jaccard(frozenset({"a", "b"}), frozenset({"a", "b"})) == 1.0
    assert jaccard(frozenset(), frozenset()) == 0.0


def test_pairwise_overlap_covers_every_pair_once():
    overlap = pairwise_title_overlap(
        {"SECURITY": ["Data export bypasses sign-off"], "QA": ["No regression plan"], "BA": []}
    )
    assert set(overlap) == {("BA", "QA"), ("BA", "SECURITY"), ("QA", "SECURITY")}
    assert overlap[("QA", "SECURITY")] == 0.0


def test_pairwise_overlap_is_case_and_punctuation_insensitive():
    overlap = pairwise_title_overlap({"A": ["Data Export!"], "B": ["data-export"]})
    assert overlap[("A", "B")] == 1.0


def test_cited_documents_resolves_known_ids_and_marks_unknown():
    names = cited_documents(
        [f"DOC-{DOC}-CHUNK-0", f"DOC-{uuid.uuid4()}-CHUNK-2", "garbage"],
        {DOC: "security-policy.md"},
    )
    assert names == ["security-policy.md", "?", "?"]


def test_summarize_shows_decision_rules_and_cited_policy():
    reviews = [
        {
            "agent": "SECURITY",
            "status": "BLOCK",
            "score": 20,
            "confidence": 0.9,
            "findings": [
                {
                    "severity": "CRITICAL",
                    "category": "MISSING_APPROVAL",
                    "evidence_status": "OK",
                    "title": "Data Governance sign-off bypassed",
                    "evidence_ids": [f"DOC-{DOC}-CHUNK-1"],
                }
            ],
        },
        {"agent": "QA", "status": "WARNING", "score": 70, "confidence": 0.8, "findings": []},
    ]
    decision = {"status": "BLOCKED", "review_complete": True, "rule_ids": ["B1_AGENT_BLOCK", "B2_CRITICAL_FINDING"]}

    text = "\n".join(summarize(reviews, decision, {DOC: "security-policy.md"}))

    assert "DECISION: BLOCKED" in text
    assert "B2_CRITICAL_FINDING" in text
    assert "<- security-policy.md" in text
    assert text.index("QA") < text.index("SECURITY")
    assert "MAX TITLE OVERLAP" in text


def test_summarize_without_decision():
    assert "DECISION: none" in summarize([], None, {})


def test_main_exits_nonzero_when_demo_request_is_not_seeded(db_session, monkeypatch, capsys):
    monkeypatch.setattr(board_run, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)

    assert board_run.main([]) == 1
    assert "Demo request not found" in capsys.readouterr().err
