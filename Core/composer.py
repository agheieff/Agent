import logging
import json
import datetime
from typing import List, Dict, Any, Tuple

logger=logging.getLogger(__name__)

class ToolResponseComposer:
    def __init__(self):
        self.conversation_start_time=datetime.datetime.now()
        self.last_update_time=self.conversation_start_time
        self.turn_counter=0
        self.total_tokens=0
        self.composers={}
        self.default_format="text"
        self.register_composer("text",TextFormatComposer())
        self.register_composer("json",JSONFormatComposer())

    def register_composer(self,name,strategy):
        self.composers[name]=strategy

    def set_default_format(self,name):
        if name in self.composers:
            self.default_format=name

    def format_tool_result(self,tool:str,params:Dict[str,Any],result:Dict[str,Any],format_name:str=None)->Any:
        f=format_name or self.default_format
        if f in self.composers:
            return self.composers[f].format_tool_result(tool,params,result)
        return result

    def compose_response(self,tool_results:List[Tuple[str,Dict[str,Any],Dict[str,Any]]],format_name:str=None)->Any:
        f=format_name or self.default_format
        if f in self.composers:
            return self.composers[f].compose_response(tool_results)
        return str(tool_results)

    def update_token_count(self,x:int):
        self.total_tokens+=x

class TextFormatComposer:
    def format_tool_result(self,tool:str,params:Dict[str,Any],result:Dict[str,Any])->str:
        s="Success"if result.get("success",False)else"Failed"
        o=result.get("output","")if result.get("success",False)else result.get("error","")
        p=", ".join(f"{k}={v}" for k,v in params.items())
        return f"Tool: {tool}\nParameters: {p}\nStatus: {s}\nOutput:\n{o}"

    def compose_response(self,x:List[Tuple[str,Dict[str,Any],Dict[str,Any]]])->str:
        if not x:
            return"No tools were executed."
        p=["I've executed the following tools:"]
        for t,pr,r in x:
            p.append(self.format_tool_result(t,pr,r))
        p.append("Please continue based on these results.")
        return"\n\n".join(p)

class JSONFormatComposer:
    def format_tool_result(self,tool:str,params:Dict[str,Any],result:Dict[str,Any])->Dict[str,Any]:
        return{"tool":tool,"params":params,"success":result.get("success",False),"output":result.get("output",""),"error":result.get("error",""),"exit_code":0 if result.get("success",False)else 1,"timestamp":datetime.datetime.now().isoformat()}

    def compose_response(self,x:List[Tuple[str,Dict[str,Any],Dict[str,Any]]])->str:
        r=[self.format_tool_result(a,b,c)for a,b,c in x]
        return json.dumps({"results":r,"message":"Tool execution complete."if x else"No tools were executed."},indent=2)
