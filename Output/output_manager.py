import sys
import asyncio
from typing import Dict,Any,List,Tuple
import logging

logger=logging.getLogger(__name__)

class OutputManager:
    def __init__(self):
        self.tool_formatters={}
        self._register_default_formatters()

    def _register_default_formatters(self):
        self.register_formatter("default",self._default_formatter)
        self.register_formatter("error",self._error_formatter)
        self.register_formatter("command",self._command_formatter)
        self.register_formatter("file_content",self._file_content_formatter)
        self.register_formatter("file_operation",self._file_operation_formatter)
        self.register_formatter("http_request",self._http_request_formatter)
        self.register_formatter("telegram",self._telegram_formatter)
        self.register_formatter("telegram_messages",self._telegram_messages_formatter)
        self.register_formatter("status",self._status_formatter)
        self.register_formatter("user_interaction",self._user_interaction_formatter)
        self.register_formatter("agent_message",self._agent_message_formatter)
        self.register_formatter("conversation_end",self._conversation_end_formatter)
        self.register_formatter("api_usage",self._api_usage_formatter)
        self.register_formatter("api_usage_summary",self._api_usage_summary_formatter)

    def register_formatter(self,name:str,f):
        self.tool_formatters[name]=f

    async def handle_tool_output(self,tool_name:str,output:Dict[str,Any])->str:
        n=output.get("formatter",tool_name)
        frm=self.tool_formatters.get(n,self.tool_formatters["default"])
        x=await frm(output)
        self.display_output(x)
        return x

    async def handle_tool_outputs(self,t:List[Tuple[str,Dict[str,Any]]])->List[str]:
        r=[]
        for n,o in t:
            x=await self.handle_tool_output(n,o)
            r.append(x)
        return r

    def display_output(self,x:str):
        print(x)
        sys.stdout.flush()

    async def get_user_input(self,p:str="> ")->str:
        print(p,end="",flush=True)
        loop=asyncio.get_event_loop()
        x=await loop.run_in_executor(None,sys.stdin.readline)
        return x.rstrip("\n")

    async def get_user_confirmation(self,p:str="Confirm? [y/N]: ")->bool:
        x=await self.get_user_input(p)
        return x.lower()in["y","yes"]

    async def _default_formatter(self,o:Dict[str,Any])->str:
        if isinstance(o,dict):
            if"error"in o and o["error"]:
                return f"Error: {o['error']}"
            elif"output"in o:
                return str(o["output"])
            return str(o)
        return str(o)

    async def _error_formatter(self,o:Dict[str,Any])->str:
        return f"Error: {o.get('error','Unknown error')}"

    async def _command_formatter(self,o:Dict[str,Any])->str:
        c=o.get("output","")
        e=o.get("exit_code",0)
        d=o.get("command","")
        if e!=0:
            er=o.get("error","")
            return f"Command failed (exit code {e}):\n$ {d}\n{er}\n{c}"
        return f"$ {d}\n{c}"

    async def _file_content_formatter(self,o:Dict[str,Any])->str:
        if not o.get("success",False):
            return f"Error: {o.get('error','Unknown error')}"
        if o.get("binary",False):
            return f"[Binary file: {o.get('file_path','unknown')}]"
        fp=o.get("file_path","")
        t=o.get("truncated",False)
        lc=o.get("line_count",0)
        off=o.get("offset",0)
        s=f"File: {fp}\nLines {off+1}-{off+lc}"
        if t:
            s+=" (truncated)"
        return s+"\n---\n"+o.get("content","")

    async def _file_operation_formatter(self,o:Dict[str,Any])->str:
        if not o.get("success",False):
            return f"Error: {o.get('error','File operation failed')}"
        a=o.get("action","")
        f=o.get("file_path","")
        if a=="create"or o.get("created",False):
            fs=o.get("file_size",0)
            return f"Created file: {f} ({fs} bytes)"
        elif a=="edit"or o.get("edited",False):
            return f"Edited file: {f}"
        return o.get("output",f"File operation completed on {f}")

    async def _http_request_formatter(self,o:Dict[str,Any])->str:
        if not o.get("success",False):
            return f"Error: {o.get('error','HTTP request failed')}"
        m=o.get("method","GET")
        u=o.get("url","")
        sc=o.get("status_code",0)
        s=f"{m} {u} - Status: {sc}\n\n"
        if sc>=400:
            s+="Error Response:\n"
        s+=o.get("response_body","")
        return s

    async def _telegram_formatter(self,o:Dict[str,Any])->str:
        if not o.get("success",False):
            return f"Error: {o.get('error','Telegram API error')}"
        msg=o.get("message","")
        cid=o.get("chat_id","")
        st=o.get("sent",False)
        if st:
            return f"Message sent to Telegram chat {cid}:\n{msg}"
        return o.get("output","Unknown status")

    async def _telegram_messages_formatter(self,o:Dict[str,Any])->str:
        if not o.get("success",False):
            return f"Error: {o.get('error','Telegram API error')}"
        mm=o.get("messages",[])
        if not mm:
            return"No Telegram messages available"
        s="Recent Telegram messages:\n\n"
        for m in mm:
            s+=f"From: {m.get('sender','Unknown')}\nMessage: {m.get('text','')}\n------------------\n"
        return s

    async def _status_formatter(self,o:Dict[str,Any])->str:
        if not o.get("success",False):
            return f"Error: {o.get('error','Operation failed')}"
        return o.get("output","Operation completed successfully")

    async def _user_interaction_formatter(self,o:Dict[str,Any])->str:
        if not o.get("success",False):
            return f"Error: {o.get('error','Failed to get user input')}"
        return""

    async def _agent_message_formatter(self,o:Dict[str,Any])->str:
        if not o.get("success",False):
            return f"Error: {o.get('error','Message delivery failed')}"
        return o.get("message","")

    async def _conversation_end_formatter(self,o:Dict[str,Any])->str:
        return"Conversation has ended."

    async def _api_usage_formatter(self,o:Dict[str,Any])->str:
        if not o.get("success",False):
            return f"Error: {o.get('error','API usage tracking failed')}"
        c=o.get("cost",0.0)
        return f"\n[API USAGE] Cost: ${c:.6f}"

    async def _api_usage_summary_formatter(self,o:Dict[str,Any])->str:
        if not o.get("success",False):
            return f"Error: {o.get('error','API usage summary failed')}"
        t=o.get("total_cost",0.0)
        return f"\nTotal API Cost: ${t:.6f}"

output_manager=OutputManager()
