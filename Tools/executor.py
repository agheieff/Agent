import inspect
import logging
import asyncio
from typing import Dict,Any,List

logger=logging.getLogger(__name__)
_TOOLS:Dict[str,Any]={}
TEST_MODE:bool=False
RESTRICT_INTERNET:bool=False

async def execute_tool(name:str,params:Dict[str,Any])->Dict[str,Any]:
    h=_TOOLS.get(name)
    if h is None:
        return{"result":f"Unknown tool: {name}","exit_code":1,"tool_name":name}
    if TEST_MODE and(not getattr(h,"test_mode_allowed",False)):
        return{"result":f"Tool {name} skipped in test mode","exit_code":0,"tool_name":name}
    if RESTRICT_INTERNET and getattr(h,"internet_tool",False):
        return{"result":f"Tool {name} skipped (internet restricted)","exit_code":1,"tool_name":name}
    logger.debug(f"Executing tool: {name} with {params}")
    try:
        if inspect.iscoroutinefunction(h):
            r=await h(**params)
        else:
            loop=asyncio.get_event_loop()
            r=await loop.run_in_executor(None,lambda:h(**params))
        if not isinstance(r,dict):
            r={"exit_code":0,"output":str(r)}
        e=r.get("exit_code",0)
        o=r.get("output","")
        er=r.get("error","")
        c=o if e==0 else er
        return{"result":c,"exit_code":e,"tool_name":name}
    except Exception as e:
        logger.error(f"Error {name}: {e}",exc_info=True)
        return{"result":str(e),"exit_code":1,"tool_name":name}

async def execute_tool_calls(tc:List[Dict[str,Any]])->List[Dict[str,Any]]:
    r=[]
    for c in tc:
        n=c.get("name")
        p=c.get("params",{})
        x=await execute_tool(n,p)
        r.append(x)
    return r
