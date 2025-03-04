import os
from typing import Dict,Any

TOOL_NAME="edit"
TOOL_DESCRIPTION="Edit a file by replacing old with new"
EXAMPLES={"file_path":"/tmp/file.txt","old":"v1","new":"v2"}
FORMATTER="file_operation"

def _ensure_absolute_path(path:str)->str:
    if not os.path.isabs(path):
        return os.path.abspath(os.path.join(os.getcwd(),path))
    return path

def tool_edit(file_path:str,old:str,new:str,**kwargs)->Dict[str,Any]:
    if not file_path:
        return{"output":"","error":"Missing file_path","exit_code":1}
    if old is None:
        return{"output":"","error":"Missing old","exit_code":1}
    if new is None:
        return{"output":"","error":"Missing new","exit_code":1}
    a=_ensure_absolute_path(file_path)
    if not os.path.exists(a):
        if old=="":
            d=os.path.dirname(a)
            if d and not os.path.exists(d):
                try:
                    os.makedirs(d,exist_ok=True)
                except Exception as e:
                    return{"output":"","error":f"Error creating dir: {str(e)}","exit_code":1,"file_path":a}
            try:
                with open(a,"w",encoding="utf-8")as f:
                    f.write(new)
                return{"output":f"Created new file: {a}","error":"","exit_code":0,"file_path":a}
            except Exception as e:
                return{"output":"","error":f"Error creating file: {str(e)}","exit_code":1,"file_path":a}
        return{"output":"","error":f"File not found: {a}","exit_code":1,"file_path":a}
    try:
        with open(a,"r",encoding="utf-8",errors="replace")as f:
            c=f.read()
    except Exception as e:
        return{"output":"","error":f"Error reading file: {str(e)}","exit_code":1,"file_path":a}
    o=c.count(old)
    if o==0:
        return{"output":"","error":f"Target string not found in {a}","exit_code":1,"file_path":a}
    if o>1:
        return{"output":"","error":f"Target string appears {o} times in {a}. Must be unique.","exit_code":1,"file_path":a}
    n=c.replace(old,new,1)
    try:
        with open(a,"w",encoding="utf-8")as f:
            f.write(n)
        return{"output":f"Edited file: {a}","error":"","exit_code":0,"file_path":a}
    except Exception as e:
        return{"output":"","error":f"Error writing file: {str(e)}","exit_code":1,"file_path":a}

def display_format(params:Dict[str,Any],result:Dict[str,Any])->str:
    f=result.get("file_path","")
    if result.get("exit_code",1)==0:
        return f"[EDIT] Success: {f}"
    return f"[EDIT] Error: {result.get('error','Unknown error')}"
