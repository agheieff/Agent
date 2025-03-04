import os
import requests
from typing import Dict,Any

TOOL_NAME="telegram_view"
TOOL_DESCRIPTION="View telegram messages"
EXAMPLES={"limit":5,"offset":0,"token":"123"}
FORMATTER="telegram_messages"

def tool_telegram_view(limit:int=5,offset:int=None,token:str=None,config:Dict[str,Any]=None,**kwargs)->Dict[str,Any]:
    if not token or not token.strip():
        if config:
            token=config.get("telegram",{}).get("token","")
    if not token.strip():
        token=os.getenv("TELEGRAM_BOT_TOKEN","")
    if not token.strip():
        return{"output":"","error":"No Telegram bot token","success":False,"exit_code":1}
    try:
        u=f"https://api.telegram.org/bot{token}/getUpdates"
        pm={}
        if offset is not None:
            pm["offset"]=offset
        r=requests.get(u,params=pm,timeout=15)
        r.raise_for_status()
        d=r.json()
        if not d.get("ok"):
            return{"output":"","error":f"Telegram API error: {d}","success":False,"exit_code":1}
        mm=d.get("result",[])
        if not mm:
            return{"output":"No new messages.","error":"","success":True,"exit_code":0,"messages":[]}
        mm=mm[-limit:]
        ff=[]
        for m in mm:
            i=m.get("update_id")
            ms=m.get("message")
            t=""
            s=""
            if ms:
                t=ms.get("text","")
                si=ms.get("from",{})
                s=si.get("username")or si.get("first_name","")
            ff.append({"update_id":i,"sender":s,"text":t,"raw":m})
        return{"output":f"Fetched {len(ff)} messages.","error":"","success":True,"exit_code":0,"messages":ff}
    except Exception as e:
        return{"output":"","error":f"Telegram API error: {str(e)}","success":False,"exit_code":1}
