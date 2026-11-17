"""Structured process logs; request code supplies route templates, never raw URLs."""
import json
import logging


class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({'level': record.levelname, 'logger': record.name,
                           'message': record.getMessage()}, ensure_ascii=False)


def configure():
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
