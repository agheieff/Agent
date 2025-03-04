import os
import logging
from typing import Dict,Any

TOOL_NAME="read"
TOOL_DESCRIPTION="Read a text file with offset,limit"
EXAMPLES={"file_path":"/etc/hosts","offset":0,"limit":2000}
FORMATTER="file_content"
logger=logging.getLogger(__name__)

def _ensure_absolute_path(path:str)->str:
    if not os.path.isabs(path):
        return os.path.abspath(os.path.join(os.getcwd(),path))
    return path

def _is_binary_file(f:str)->bool:
    try:
        with open(f,"rb")as x:
            c=x.read(4096)
            return b"\0"in c
    except:
        return False

async def tool_read(file_path:str,offset:int=0,limit:int=2000,**kwargs)->Dict[str,Any]:
    if not file_path:
        return{"output":"","error":"Missing file_path","exit_code":1}
    a=_ensure_absolute_path(file_path)
    if not os.path.exists(a):
        return{"output":"","error":f"File not found: {a}","exit_code":1,"file_path":a}
    if os.path.isdir(a):
        return{"output":"","error":f"Path is a directory: {a}","exit_code":1,"file_path":a}
    try:
        offset=int(offset)
        limit=int(limit)
        if offset<0 or limit<=0:
            raise ValueError
    except:
        return{"output":"","error":"Offset must be >=0 and limit>0","exit_code":1}
    if _is_binary_file(a):
        return{"output":f"Binary file: {a}","error":"","exit_code":0,"file_path":a,"binary":True}
    c=[]
    t=False
    try:
        with open(a,"r",encoding="utf-8",errors="replace")as f:
            for _ in range(offset):
                if not next(f,None):
                    break
            for _ in range(limit):
                d=next(f,None)
                if d is None:
                    break
                c.append(d)
            if next(f,None)is not None:
                t=True
    except Exception as e:
        return{"output":"","error":f"Error reading file: {str(e)}","exit_code":1,"file_path":a}
    r=len(c)
    s=f"Read {r} lines from {a}"
    if t:
        s+=" (truncated)"
    return{"output":s,"error":"","exit_code":0,"file_path":a,"content":"".join(c),"truncated":t,"binary":False,"line_count":r,"offset":offset}

def display_format(params:Dict[str,Any],result:Dict[str,Any])->str:
    if result.get("exit_code",1)==0:
        i=result.get("output","")
        if result.get("truncated",False):
            i+=" [truncated]"
        return f"[READ] {i}"
    return f"[READ] Error: {result.get('error','Unknown error')}"
