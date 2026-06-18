import json
import sys
import logging

logging.disable(logging.CRITICAL)

from agent import collect_all

query = " ".join(sys.argv[1:])

data = collect_all(
    query,
    max_per_source=10
)

print(json.dumps(data))
