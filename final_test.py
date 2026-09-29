"""
Final end-to-end test — runs the full pipeline directly without FastAPI
so .env changes are picked up immediately.
"""
import os
os.chdir(r'c:\Users\raghi\OneDrive\Desktop\Decision_Graveyard_agent')
from dotenv import load_dotenv
load_dotenv(override=True)   # force reload even if already loaded

from retrieval import query_proposal, get_debt_score, get_full_log

PASS = []
FAIL = []

def check(label, condition):
    if condition:
        print(f"  PASS  {label}")
        PASS.append(label)
    else:
        print(f"  FAIL  {label}")
        FAIL.append(label)

# Q1 — chatbot with NO fallback  →  expect HIGH match on DEC-011
print("Q1: chatbot NO fallback")
r1 = query_proposal("Deploy a fully automated chatbot for all tier-1 support tickets with no human fallback.")
print("  Message:", r1.message[:110])
for e in r1.surfaced:
    print(f"    [{e.confidence.upper()}] {e.decision_id} | {e.confidence_explanation[:80]}")
check("Q1 has matches", len(r1.surfaced) > 0)
check("Q1 includes DEC-011", any(e.decision_id == "DEC-011" for e in r1.surfaced))

print()

# Q2 — chatbot WITH human review  →  expect DEC-011 surfaced (medium/high)
print("Q2: chatbot WITH human escalation")
r2 = query_proposal("Deploy an AI chatbot for support but keep a human escalation path for edge cases.")
print("  Message:", r2.message[:110])
for e in r2.surfaced:
    print(f"    [{e.confidence.upper()}] {e.decision_id} | {e.confidence_explanation[:80]}")
check("Q2 has matches", len(r2.surfaced) > 0)
check("Q2 includes DEC-011", any(e.decision_id == "DEC-011" for e in r2.surfaced))

print()

# Q3 — unrelated  →  expect no surfaced matches
print("Q3: loyalty programme (unrelated)")
r3 = query_proposal("Launch a new loyalty programme for repeat customers.")
print("  Message:", r3.message[:110])
check("Q3 no false positives", len(r3.surfaced) == 0)

print()

# Debt score and log
ds  = get_debt_score()
log = get_full_log()
print("Debt score:", ds["summary"])
print("Log: evaluated=%d  surfaced=%d  rejected=%d" % (
    log["total_candidates_evaluated"], log["surfaced_count"], log["rejected_count"]))

check("Debt score counts queries", ds["total_queries"] >= 3)
check("Log has candidates", log["total_candidates_evaluated"] > 0)

print()
print("=" * 50)
print(f"PASSED: {len(PASS)}/{len(PASS)+len(FAIL)}")
if FAIL:
    print("FAILED:", FAIL)
else:
    print("ALL TESTS PASSED - agent is working end-to-end")
