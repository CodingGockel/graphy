"""Container liveness probe.

Succeeds as long as the API answers HTTP at all — including a 503 from
/api/v1/health, which signals a dependency (GraphDB/LLM) is unreachable rather
than the process being dead. Fails only when the server cannot be contacted.
Use GET /api/v1/health directly for readiness/monitoring.
"""

import sys
import urllib.error
import urllib.request

URL = "http://localhost:8000/api/v1/health"

try:
    urllib.request.urlopen(URL, timeout=4)
except urllib.error.HTTPError:
    # Got an HTTP response (e.g. 503) — the process is alive.
    sys.exit(0)
except Exception:
    # Connection refused / timeout / DNS — not alive.
    sys.exit(1)
sys.exit(0)
