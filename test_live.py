"""
End-to-end live test. Run with: python test_live.py
"""
import httpx, json

BASE = "http://localhost:8000"

# 1. Status
st = httpx.get(f"{BASE}/status").json()
print("=== STATUS ===")
print("  Hindsight reachable :", st["hindsight_reachable"])
print("  Groq key set        :", st["groq_key_set"])
print("  LLM mode            :", st["llm_mode"])
print("  Bank loaded         :", st["bank_loaded"])
print()

# 2. /check — chatbot with NO fallback  →  expect HIGH match DEC-011
print("=== QUERY 1: chatbot no fallback (expect HIGH match) ===")
r = httpx.post(
    f"{BASE}/check",
    json={"proposal": "Deploy a fully automated chatbot for all tier-1 support tickets with no human fallback."},
    timeout=60,
).json()
print("  Message :", r["message"])
print("  Surfaced:", len(r["surfaced"]), "  Rejected:", len(r["rejected"]))
for e in r["surfaced"]:
    print(f"  [{e['confidence'].upper()}] {e['decision_id']} — {e['confidence_explanation']}")
print()

# 3. /check — chatbot WITH human review  →  expect MEDIUM nuanced
print("=== QUERY 2: chatbot WITH human escalation (expect MEDIUM/nuanced) ===")
r2 = httpx.post(
    f"{BASE}/check",
    json={"proposal": "Deploy an AI chatbot for support tickets but keep a human escalation path for complex issues."},
    timeout=60,
).json()
print("  Message :", r2["message"])
print("  Surfaced:", len(r2["surfaced"]), "  Rejected:", len(r2["rejected"]))
for e in r2["surfaced"]:
    print(f"  [{e['confidence'].upper()}] {e['decision_id']} — {e['confidence_explanation']}")
print()

# 4. /debt-score
ds = httpx.get(f"{BASE}/debt-score").json()
print("=== DEBT SCORE ===")
print(" ", ds["summary"])
print()

# 5. /log
log = httpx.get(f"{BASE}/log").json()
print("=== CANDIDATE LOG ===")
print("  Total evaluated :", log["total_candidates_evaluated"])
print("  Surfaced        :", log["surfaced_count"])
print("  Rejected        :", log["rejected_count"])
print()
print("All endpoints working.")
