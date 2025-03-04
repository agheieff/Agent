import json
import logging
import re
from typing import Dict,Any

logger=logging.getLogger(__name__)

class ToolParser:
    def parse_message(self,message:str)->Dict[str,Any]:
        r={"tool_calls":[]}
        try:
            # Clean message and try direct parsing
            clean_msg=message.strip()
            # Try to extract JSON if wrapped in code blocks
            if "```json" in clean_msg:
                match=re.search(r'```json\s*(.*?)\s*```',clean_msg,re.DOTALL)
                if match:
                    clean_msg=match.group(1)
            d=json.loads(clean_msg)
            if isinstance(d,dict):
                if"tool_calls"not in d:
                    d["tool_calls"]=[]
                return d
        except Exception as e:
            logger.debug(f"JSON parse failed: {e}")
        return r
