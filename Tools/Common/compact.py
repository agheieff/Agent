from typing import Dict,Any,List
from Prompts.compact import get_compact_prompt

TOOL_NAME="compact"
TOOL_DESCRIPTION="Summarize the conversation so far"
EXAMPLES={}
FORMATTER="status"

async def tool_compact(conversation_history:List[Dict[str,str]]=None,llm:Any=None,**kwargs)->Dict[str,Any]:
    if not conversation_history or not isinstance(conversation_history,list):
        return{"output":"","error":"No valid conversation history","exit_code":1}
    if not llm:
        return{"output":"","error":"No LLM provided","exit_code":1}
    u=[m["content"]for m in conversation_history if m["role"]in("user","assistant")]
    if not u:
        return{"output":"No user or assistant messages","error":"","exit_code":0}
    c="\n".join(u)
    p=get_compact_prompt()
    try:
        s=await llm.get_response(prompt=p,system=None,conversation_history=[{"role":"user","content":c}],temperature=0.5,max_tokens=1024)
        sc=conversation_history[0]["content"]if conversation_history and conversation_history[0]["role"]=="system"else None
        conversation_history.clear()
        if sc:
            conversation_history.append({"role":"system","content":sc})
        conversation_history.append({"role":"assistant","content":s or""})
        return{"output":"Conversation compacted.","error":"","exit_code":0,"summary":s or""}
    except Exception as e:
        return{"output":"","error":f"Error generating summary: {str(e)}","exit_code":1}

def display_format(params:Dict[str,Any],result:Dict[str,Any])->str:
    if result.get("exit_code",1)==0:
        return"[COMPACT]"
    return f"[COMPACT] Error: {result.get('error','Unknown error')}"
