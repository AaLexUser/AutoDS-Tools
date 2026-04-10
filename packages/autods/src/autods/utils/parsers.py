import json
import logging
import re
from typing import Any, Dict

import json_repair

logger = logging.getLogger(__name__)


def parse_json(raw_reply: str | None) -> Dict[str, Any] | None:
    """Parse a JSON string from the raw reply."""
    if not raw_reply:
        logger.warning("Received empty or None raw reply for JSON parsing.")
        return None

    def try_json_loads(data: str) -> Dict[str, Any] | None:
        try:
            repaired_json = json_repair.repair_json(
                data, ensure_ascii=False, return_objects=True
            )
            if isinstance(repaired_json, dict) and repaired_json != "":
                return repaired_json
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON decoding error: {e}")
            return None

    raw_reply = raw_reply.strip()
    # Case 1: Check if the JSON is enclosed in triple backticks
    json_match = re.search(r"\{.*\}|```(?:json)?\s*(.*?)```", raw_reply, re.DOTALL)
    if json_match:
        if json_match.group(1):
            reply_str = json_match.group(1).strip()
        else:
            reply_str = json_match.group(0).strip()
        reply = try_json_loads(reply_str)
        if reply is not None:
            return reply

    # Case 2: Assume the entire string is a JSON object
    return try_json_loads(raw_reply)
