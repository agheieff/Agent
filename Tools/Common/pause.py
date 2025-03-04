import logging
from typing import Dict,Any

TOOL_NAME="pause"
TOOL_DESCRIPTION="Pause for user input"
EXAMPLES={"message":"Please provide input"}
FORMATTER="user_interaction"

logger=logging.getLogger(__name__)

async def tool_pause(message:str,output_manager=None,**kwargs)->Dict[str,Any]:
    if not message:
        return{"output":"","error":"Missing message","exit_code":1}
    if output_manager is None:
        return{"output":"","error":"No output_manager","exit_code":1}
    try:
        u=await output_manager.get_user_input(f"{message} ")
        return{"output":f"Received user input: {u}","error":"","exit_code":0,"user_input":u,"prompt_message":message}
    except Exception as e:
        logger.exception("Error in pause tool")
        return{"output":"","error":f"Error getting input: {str(e)}","exit_code":1}

def display_format(params:Dict[str,Any],result:Dict[str,Any])->str:
    m=params.get("message","")
    i=result.get("user_input","")
    if result.get("exit_code",1)==0:
        return f"[PAUSE] Prompt: {m}\nUser input: {i}"
    return f"[PAUSE] Error: {result.get('error','Unknown error')}"
