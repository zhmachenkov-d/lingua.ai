"""Fixed MVP identity constants (AD-10).

One hardcoded local learner — no multi-user auth in MVP.
"""

import uuid

# Singleton MVP learner. Routes, tests, and docs must import this symbol —
# do not redefine it in HTTP route modules.
MVP_LEARNER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
