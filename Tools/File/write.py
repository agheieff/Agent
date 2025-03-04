import os
import logging
from typing import Dict,Any

TOOL_NAME="write"
TOOL_DESCRIPTION="Create a new file with content"
EXAMPLES={"file_path":"/tmp/newfile.txt","content":"Hello","mkdir":True}
FORMATTER="file_operation"
logger=logging.getLogger(__name__)

def _ensure_absolute_path(path:str)->str:
    if not os.path.isabs(path):
        return os.path.abspath(os.path.join(os.getcwd(),path))
    return path

async def tool_write(file_path:str,content:str,mkdir:bool=True,**kwargs)->Dict[str,Any]:
    if not file_path:
        return{"output":"","error":"Missing file_path","exit_code":1}
    if content is None:
        return{"output":"","error":"Missing content","exit_code":1}
    a=_ensure_absolute_path(file_path)
    if os.path.exists(a):
        return{"output":"","error":f"File exists: {a}","exit_code":1,"file_path":a}
    d=os.path.dirname(a)
    if d and not os.path.exists(d):
        if mkdir:
            try:
                os.makedirs(d,exist_ok=True)
            except Exception as e:
                return{"output":"","error":f"Error creating dir: {str(e)}","exit_code":1,"file_path":a}
        else:
            return{"output":"","error":f"Parent dir missing: {d}","exit_code":1,"file_path":a}
    try:
        with open(a,"w",encoding="utf-8")as f:
            f.write(content)
        fs=os.path.getsize(a)
        return{"output":f"Created file: {a}","error":"","exit_code":0,"file_path":a,"file_size":fs}
    except Exception as e:
        return{"output":"","error":f"Error writing file: {str(e)}","exit_code":1,"file_path":a}

def display_format(params:Dict[str,Any],result:Dict[str,Any])->str:
    f=result.get("file_path","")
    if result.get("exit_code",1)==0:
        return f"[WRITE] File created: {f}"
    return f"[WRITE] Error: {result.get('error','Unknown error')}"
