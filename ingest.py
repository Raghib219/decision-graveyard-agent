"""
Ingest the Nimbus Retail decision dataset into Hindsight Cloud.

Usage:
    python ingest.py              # load the 28-record dataset
    python ingest.py --clear      # wipe the bank first, then reload
    python ingest.py --status     # show bank status
"""

import argparse
import httpx
import os
import sys
import time

from dotenv import load_dotenv
from hindsight_client import Hindsight

from convert_to_nl import convert_all, decision_to_nl

load_dotenv()

HINDSIGHT_URL     = os.getenv("HINDSIGHT_URL",     "https://api.hindsight.vectorize.io")
HINDSIGHT_API_KEY = os.getenv("HINDSIGHT_API_KEY", "")
BANK_ID           = os.getenv("BANK_ID",           "decision-graveyard")


# ── client factory ────────────────────────────────────────────────────

def get_client() -> Hindsight:
    if HINDSIGHT_API_KEY:
        return Hindsight(base_url=HINDSIGHT_URL, api_key=HINDSIGHT_API_KEY, timeout=60.0)
    return Hindsight(base_url=HINDSIGHT_URL, timeout=60.0)


def ensure_bank(client: Hindsight) -> None:
    """Create the bank if it doesn't exist. Safe to call repeatedly."""
    try:
        client.create_bank(bank_id=BANK_ID, name="Decision Graveyard — Nimbus Retail")
    except Exception:
        pass  # already exists — fine


def check_server(client: Hindsight) -> bool:
    """Return True when Hindsight Cloud is reachable with the current key."""
    try:
        # recall on an empty bank returns [] — that is a valid success response
        client.recall(bank_id=BANK_ID, query="test", max_tokens=10)
        return True
    except Exception as e:
        err = str(e).lower()
        # 404 = bank doesn't exist yet, server IS reachable
        if "404" in err or "not found" in err:
            return True
        return False


# ── bank operations ───────────────────────────────────────────────────

def wipe_bank(client: Hindsight) -> None:
    """Clear all memories from the bank using the REST API directly."""
    print(f"Wiping bank '{BANK_ID}' …")
    try:
        headers = {"Authorization": f"Bearer {HINDSIGHT_API_KEY}"}
        url = f"{HINDSIGHT_URL}/v1/default/banks/{BANK_ID}/memories"
        resp = httpx.delete(url, headers=headers, timeout=30)
        if resp.status_code in (200, 204):
            print("  All memories cleared.")
        elif resp.status_code == 404:
            print("  Bank is empty or doesn't exist yet.")
        else:
            print(f"  Clear returned HTTP {resp.status_code} — proceeding (records will be upserted).")
    except Exception as e:
        print(f"  Could not clear ({e}) — records will be upserted (no duplicates).")


def _retain_in_thread(record_data: dict) -> None:
    """Run retain() in a fresh thread with a new client instance (no event loop)."""
    # Create a fresh client instance in this thread
    if HINDSIGHT_API_KEY:
        client = Hindsight(base_url=HINDSIGHT_URL, api_key=HINDSIGHT_API_KEY, timeout=60.0)
    else:
        client = Hindsight(base_url=HINDSIGHT_URL, timeout=60.0)
    
    client.retain(**record_data)


def ingest_dataset(client: Hindsight, dataset_path: str = "data/dataset.json") -> int:
    """Convert each record to NL and retain in Hindsight. Returns count stored."""
    ensure_bank(client)
    records = convert_all(dataset_path)
    total   = len(records)
    print(f"\nIngesting {total} records into '{BANK_ID}' …")
    print(f"URL: {HINDSIGHT_URL}  |  key: {'set' if HINDSIGHT_API_KEY else 'not set'}\n")

    success = 0
    for i, rec in enumerate(records, 1):
        dec_id  = rec["decision_id"]
        outcome = rec["outcome"]
        team    = rec["team"]
        date    = rec["date"]
        try:
            record_data = {
                "bank_id": BANK_ID,
                "content": rec["nl_text"],
                "document_id": dec_id,
                "context": f"Decision record — {team}, outcome: {outcome}",
                "timestamp": date,
                "metadata": {
                    "decision_id": dec_id,
                    "outcome":     outcome,
                    "team":        team,
                    "date":        date,
                },
            }
            # Run in isolated thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_retain_in_thread, record_data)
                future.result(timeout=30)
            print(f"  [{i:02d}/{total}] ✓  {dec_id} ({outcome}) — {team}")
            success += 1
        except Exception as e:
            print(f"  [{i:02d}/{total}] ✗  {dec_id} — {e}")
        time.sleep(0.2)

    print(f"\nDone: {success}/{total} records stored.")
    return success


def show_status(client: Hindsight) -> None:
    try:
        result = client.recall(bank_id=BANK_ID, query="Decision", max_tokens=200, budget="low")
        facts  = result.results if result.results else []
        print(f"\nBank '{BANK_ID}': reachable — {len(facts)} facts on sample recall")
    except Exception as e:
        print(f"Status check error: {e}")


def ingest_single(
    client: Hindsight,
    decision_id: str,
    proposal: str,
    outcome: str,
    team: str,
    date: str,
    reasoning_for: list,
    reasoning_against: list,
    evidence: str,
) -> bool:
    """Store one decision record (called by the /ingest API endpoint)."""
    ensure_bank(client)
    record = {
        "decision_id":      decision_id,
        "date":             date,
        "team":             team,
        "proposal":         proposal,
        "outcome":          outcome,
        "reasoning_for":    reasoning_for,
        "reasoning_against": reasoning_against,
        "key_people":       [],
        "outcome_evidence": evidence,
        "tags":             [],
    }
    try:
        record_data = {
            "bank_id": BANK_ID,
            "content": decision_to_nl(record),
            "document_id": decision_id,
            "context": f"Decision record — {team}, outcome: {outcome}",
            "timestamp": date,
            "metadata": {
                "decision_id": decision_id,
                "outcome":     outcome,
                "team":        team,
                "date":        date,
            },
        }
        # Run in isolated thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_retain_in_thread, record_data)
            future.result(timeout=30)
        return True
    except Exception as e:
        print(f"ingest_single error: {e}")
        return False


# ── CLI ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest decisions into Hindsight")
    parser.add_argument("--clear",   action="store_true", help="Wipe bank before loading")
    parser.add_argument("--status",  action="store_true", help="Show bank status only")
    parser.add_argument("--dataset", default="data/dataset.json")
    args = parser.parse_args()

    client = get_client()
    print(f"Connecting to Hindsight at {HINDSIGHT_URL} …")

    if not check_server(client):
        print("\nERROR: Cannot reach Hindsight Cloud. Check HINDSIGHT_API_KEY in .env")
        sys.exit(1)
    print("Connected.\n")

    if args.status:
        show_status(client)
        sys.exit(0)

    if args.clear:
        wipe_bank(client)

    ingest_dataset(client, args.dataset)
    show_status(client)
