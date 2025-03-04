import asyncio
import subprocess
from typing import Dict,Any

TOOL_NAME="bash"
TOOL_DESCRIPTION="Execute shell commands"
EXAMPLES={"command":"ls -la","timeout":60}
FORMATTER="command"

async def tool_bash(command:str,timeout:int=60,**kwargs)->Dict[str,Any]:
    if not command:
        return{"output":"","error":"Missing command","success":False,"exit_code":1}
    try:
        p=await asyncio.create_subprocess_shell(command,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        if timeout>0:
            try:
                o,e=await asyncio.wait_for(p.communicate(),timeout=timeout)
            except asyncio.TimeoutError:
                p.kill()
                return{"output":"","error":f"Command timed out after {timeout}s","success":False,"exit_code":124,"command":command}
        else:
            o,e=await p.communicate()
        so=o.decode("utf-8",errors="replace")
        se=e.decode("utf-8",errors="replace")
        s=(p.returncode==0)
        c=p.returncode
        if s:
            return{"output":f"Command executed (exit={c}): {command}","error":"","success":True,"exit_code":c,"command":command,"stdout":so,"stderr":se}
        return{"output":"","error":f"Command failed (exit={c}): {se}","success":False,"exit_code":c,"command":command,"stdout":so,"stderr":se}
    except Exception as e:
        return{"output":"","error":f"Error executing bash command: {str(e)}","success":False,"exit_code":1,"command":command}
