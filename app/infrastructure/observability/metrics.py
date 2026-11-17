"""Low-cardinality JSON metrics; no user IDs, credentials or payloads."""
import json
import logging
import sys

logger = logging.getLogger('labseat.metrics')
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


def emit(name, value=1):
    logger.info(json.dumps({'metric': name, 'value': value}, separators=(',', ':')))
