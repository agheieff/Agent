import os
import requests
from typing import Dict,Any

TOOL_NAME="telegram_send"
TOOL_DESCRIPTION="Send telegram message"
EXAMPLES={"message":"Hello","token":"123","chat_id":"456"}
FORMATTER="telegram"

def tool_telegram_send(message:str,token:str=None,chat_id:str=None,config:Dict[str,Any]=None,**kwargs)->Dict[str,Any]:
    if not token or not token.strip():
        if config:
            token=config.get("telegram",{}).get("token","")
    if not token.strip():
        token=os.getenv("TELEGRAM_BOT_TOKEN","")
    if not chat_id or not chat_id.strip():
        if config:
            chat_id=config.get("telegram",{}).get("chat_id","")
    if not chat_id.strip():
        chat_id=os.getenv("TELEGRAM_CHAT_ID","")
    if not token.strip():
        return{"output":"","error":"No Telegram bot token","success":False,"exit_code":1}
    if not chat_id.strip():
        return{"output":"","error":"No Telegram chat ID","success":False,"exit_code":1}
    if not message:
        return{"output":"","error":"No message text","success":False,"exit_code":1}
    try:
        u=f"https://api.telegram.org/bot{token}/sendMessage"
        p={"chat_id":chat_id,"text":message}
        r=requests.post(u,json=p,timeout=15)
        r.raise_for_status()
        d=r.json()
        if not d.get("ok"):
            return{"output":"","error":f"Telegram API error: {d}","success":False,"exit_code":1}
        return{"output":f"Message sent to chat {chat_id}","error":"","success":True,"exit_code":0,"message":message,"chat_id":chat_id}
    except Exception as e:
        return{"output":"","error":f"Telegram API error: {str(e)}","success":False,"exit_code":1}
