import json
import logging
from typing import Dict,Any

logger=logging.getLogger(__name__)

class ToolParser:
    def parse_message(self,message:str)->Dict[str,Any]:
        r={"tool_calls":[]}
        try:
            d=json.loads(message.strip())
            if isinstance(d,dict):
                if"tool_calls"not in d:
                    d["tool_calls"]=[]
                return d
        except Exception as e:
            logger.error(f"Failed to parse JSON: {e}")
        return r
