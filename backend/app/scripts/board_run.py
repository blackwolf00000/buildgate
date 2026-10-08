"""Runs the full review board on the seeded demo request and prints the outcome.

Run with: docker compose exec api python -m app.scripts.board_run [--runs N]

Goes through the same start_review / execute_review path as the UI, so every
run writes ordinary review, decision and audit rows.
"""
import argparse
import itertools
import re
import sys
import time

from app.db.models import AgentReview, Decision, Document, Request, ReviewRun
from app.db.session import SessionLocal
from app.scripts.seed_demo import DEMO_REQUEST
from app.services.review import execute_review, start_review

_EVIDENCE_ID = re.compile(r"^DOC-(?P<doc>[0-9a-fA-F-]{36})-CHUNK-\d+$")


def _tokens(title: str) -> frozenset[str]:
    return frozenset(re.findall(r"[a-z0-9]+", title.lower()))


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def pairwise_title_overlap(titles_by_agent: dict[str, list[str]]) -> dict[tuple[str, str], float]:
    """Jaccard overlap of each agent pair's finding-title vocabulary."""
    vocab = {
        agent: frozenset().union(*(_tokens(t) for t in titles)) if titles else frozenset()
        for agent, titles in titles_by_agent.items()
    }
    return {
        (a, b): jaccard(vocab[a], vocab[b])
        for a, b in itertools.combinations(sorted(vocab), 2)
    }


def cited_documents(evidence_ids: list[str], filenames_by_doc_id: dict[str, str]) -> list[str]:
    names = []
    for eid in evidence_ids:
        match = _EVIDENCE_ID.match(eid)
        doc_id = match.group("doc").lower() if match else None
        names.append(filenames_by_doc_id.get(doc_id, "?") if doc_id else "?")
    return names


def summarize(
    reviews: list[dict],
    decision: dict | None,
    filenames_by_doc_id: dict[str, str],
) -> list[str]:
    """Human-readable lines for one run. `reviews` are agent_reviews as plain dicts."""
    lines = []
    for r in sorted(reviews, key=lambda r: r["agent"]):
        lines.append(f"{r['agent']:<14} {r['status']:<8} score={r['score']:<3} conf={r['confidence']:.2f}")
        for f in r["findings"]:
            docs = ", ".join(cited_documents(f.get("evidence_ids", []), filenames_by_doc_id)) or "-"
            lines.append(
                f"    {f['severity']:<8} {f.get('category', '?'):<28} "
                f"[{f.get('evidence_status', '?')}] {f['title']}  <- {docs}"
            )
    if decision is None:
        lines.append("DECISION: none")
    else:
        lines.append(
            f"DECISION: {decision['status']}  complete={decision['review_complete']}  "
            f"rules={','.join(decision['rule_ids'])}"
        )
    overlap = pairwise_title_overlap(
        {r["agent"]: [f["title"] for f in r["findings"]] for r in reviews}
    )
    if overlap:
        (a, b), worst = max(overlap.items(), key=lambda kv: kv[1])
        lines.append(f"MAX TITLE OVERLAP: {worst:.2f} ({a} vs {b})")
    return lines


def _enum(v) -> str:
    return getattr(v, "value", v)


def _run_once(db, request: Request, filenames: dict[str, str]) -> None:
    started = time.monotonic()
    run = start_review(db, request, actor="board_run")
    execute_review(db, run.id)
    db.expire_all()

    run = db.get(ReviewRun, run.id)
    reviews = [
        {
            "agent": _enum(r.agent),
            "status": _enum(r.status),
            "score": r.score,
            "confidence": float(r.confidence),
            "findings": r.findings,
        }
        for r in db.query(AgentReview).filter(AgentReview.review_run_id == run.id)
    ]
    d = db.query(Decision).filter(Decision.review_run_id == run.id).first()
    decision = (
        {"status": _enum(d.status), "review_complete": d.review_complete, "rule_ids": d.rule_ids}
        if d
        else None
    )
    print(f"review_run_id={run.id} run_status={_enum(run.status)} error={run.error or '-'}")
    for line in summarize(reviews, decision, filenames):
        print(line)
    print(f"ELAPSED: {time.monotonic() - started:.0f}s")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        request = db.query(Request).filter(Request.title == DEMO_REQUEST["title"]).first()
        if request is None:
            print(
                "Demo request not found. Seed it first: "
                "docker compose exec api python -m app.scripts.seed_demo",
                file=sys.stderr,
            )
            return 1
        filenames = {
            str(doc.id).lower(): doc.original_filename
            for doc in db.query(Document).filter(Document.request_id == request.id)
        }
        for i in range(1, args.runs + 1):
            print(f"=== RUN {i}/{args.runs} ===", flush=True)
            _run_once(db, request, filenames)
            sys.stdout.flush()
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
