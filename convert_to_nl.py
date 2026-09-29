"""
Convert structured decision records to natural-language paragraphs for Hindsight ingestion.
Natural language retrieves better because it matches how real retro docs and Slack threads read.
"""

import json
from pathlib import Path


def decision_to_nl(d: dict) -> str:
    """Turn one decision record into a natural-language paragraph."""
    dec_id = d["decision_id"]
    date = d["date"]
    team = d["team"]
    proposal = d["proposal"]
    outcome = d["outcome"].replace("_", " ")

    # Build the for/against lists
    for_points = d.get("reasoning_for", [])
    against_points = d.get("reasoning_against", [])
    evidence = d.get("outcome_evidence", "")
    people = d.get("key_people", [])
    duration = d.get("duration_before_reversal", "")

    for_text = " ".join(f"({p})" for p in for_points) if for_points else ""
    against_text = " ".join(f"({p})" for p in against_points) if against_points else ""
    people_text = ", ".join(people) if people else ""

    parts = [
        f"Decision {dec_id} — {team} team, dated {date}.",
        f"Proposal: {proposal}",
        f"Outcome: {outcome}.",
    ]

    if duration:
        parts.append(f"It was reversed after {duration}.")

    if for_text:
        parts.append(f"Arguments in favor included: {for_text}.")

    if against_text:
        parts.append(f"Arguments against / reasons for failure: {against_text}.")

    if evidence:
        parts.append(f"Evidence: {evidence}.")

    if people_text:
        parts.append(f"Key people involved: {people_text}.")

    tags = d.get("tags", [])
    if tags:
        parts.append(f"Topics: {', '.join(tags)}.")

    return " ".join(parts)


def load_decisions(path: str = "data/dataset.json") -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["decisions"]


def convert_all(path: str = "data/dataset.json") -> list[dict]:
    """
    Return a list of dicts ready for Hindsight ingestion:
      { decision_id, date, team, outcome, tags, nl_text }
    """
    decisions = load_decisions(path)
    result = []
    for d in decisions:
        result.append(
            {
                "decision_id": d["decision_id"],
                "date": d["date"],
                "team": d["team"],
                "outcome": d["outcome"],
                "tags": d.get("tags", []),
                "nl_text": decision_to_nl(d),
            }
        )
    return result


if __name__ == "__main__":
    records = convert_all()
    for r in records[:2]:
        print("=" * 60)
        print(r["decision_id"], "|", r["outcome"])
        print(r["nl_text"])
    print(f"\nTotal records: {len(records)}")
