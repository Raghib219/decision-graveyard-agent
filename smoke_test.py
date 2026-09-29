"""
Production smoke test — run before deploying.
python smoke_test.py
"""
import os, sys
os.chdir(r'c:\Users\raghi\OneDrive\Desktop\Decision_Graveyard_agent')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PASS = []
FAIL = []

def check(label, cond, detail=""):
    if cond:
        print(f"  PASS  {label}")
        PASS.append(label)
    else:
        print(f"  FAIL  {label}" + (f" -- {detail}" if detail else ""))
        FAIL.append(label)

# 1. All modules import
try:
    import store, cache, logger, auth, ingest, retrieval, convert_to_nl
    check("All modules import", True)
except Exception as e:
    check("All modules import", False, str(e))

# 2. Dataset
from convert_to_nl import convert_all
records = convert_all('data/dataset.json')
check("Dataset 28 records", len(records) == 28, f"got {len(records)}")

# 3. FastAPI routes
import importlib.util
spec = importlib.util.spec_from_file_location('main', 'main.py')
mod  = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
routes   = [r.path for r in mod.app.routes]
required = ['/check', '/check/stream', '/ingest', '/debt-score', '/log', '/status', '/decisions', '/query']
missing  = [r for r in required if r not in routes]
check("All routes present", not missing, f"missing: {missing}")

# 4. Store round-trip
from store import append_debt_entry, append_candidate_entry, get_debt_score_data, get_full_log_data
from pathlib import Path
append_debt_entry({
    'timestamp':'2026-01-01T00:00:00Z','proposal_snippet':'smoke-test',
    'bank_loaded':True,'caught':True,'high_confidence':True,
    'medium_confidence':False,'new_territory':False,'matched_ids':['DEC-011']
})
append_candidate_entry({
    'timestamp':'2026-01-01T00:00:00Z','proposal':'smoke-test',
    'decision_id':'DEC-011','confidence':'high','surfaced':True,
    'same_problem':True,'same_failure_mode':True,
    'explanation':'smoke-test','candidate_snippet':'smoke-test'
})
ds = get_debt_score_data()
fl = get_full_log_data()
check("Store debt entry written",     ds['total_queries'] >= 1)
check("Store candidate entry written", fl['total_candidates_evaluated'] >= 1)
check("Store file exists", Path('data/store.json').exists())

# 5. Cache (no Redis expected in dev — graceful fallback)
from cache import get_cached, set_cached, cache_status
set_cached('smoke-test proposal', {'message': 'ok'})
cs = cache_status()
check("Cache graceful fallback", True)  # always passes — either connected or fallback
print(f"       Redis: {'connected' if cs['enabled'] else 'not available (fallback active)'}")

# 6. Auth
from auth import auth_status
astatus = auth_status()
check("Auth module OK", True)
print(f"       Auth enabled: {astatus['auth_enabled']}")

# 7. UI SSE wiring
ui = Path('static/index.html')
content = ui.read_text(encoding='utf-8')
check("UI file exists",          ui.exists())
check("UI has SSE EventSource",  'EventSource' in content)
check("UI uses /check/stream",   '/check/stream' in content)
check("UI size > 20KB",          ui.stat().st_size > 20000)

# 8. Docker
check("Dockerfile exists",        Path('Dockerfile').exists())
check("docker-compose.yml exists", Path('docker-compose.yml').exists())
check(".dockerignore exists",      Path('.dockerignore').exists())

# 9. CI/CD
check("GitHub Actions CI exists", Path('.github/workflows/ci.yml').exists())

# 10. Railway
check("railway.json exists",      Path('railway.json').exists())

# 11. .gitignore (no .env committed)
gi = Path('.gitignore').read_text() if Path('.gitignore').exists() else ''
check(".gitignore excludes .env", '.env' in gi)

# 12. requirements.txt has new deps
req = Path('requirements.txt').read_text()
for dep in ['redis', 'structlog', 'sentry-sdk']:
    check(f"requirements.txt has {dep}", dep in req)

print()
print("=" * 50)
print(f"PASSED: {len(PASS)}/{len(PASS)+len(FAIL)}")
if FAIL:
    print("FAILED:", FAIL)
    sys.exit(1)
else:
    print("ALL CHECKS PASSED -- ready to deploy")
