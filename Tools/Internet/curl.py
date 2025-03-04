import requests
from typing import Dict,Any

TOOL_NAME="curl"
TOOL_DESCRIPTION="Send HTTP request"
EXAMPLES={"method":"GET","url":"https://example.com"}
FORMATTER="http_request"

async def tool_curl(method:str="GET",url:str=None,data:str=None,headers:str=None,timeout:int=20,allow_insecure:bool=False,**kwargs)->Dict[str,Any]:
    if not url:
        return{"output":"","error":"Missing 'url' parameter","success":False,"exit_code":1}
    h={}
    if headers:
        for kv in headers.split(","):
            kv=kv.strip()
            if":"in kv:
                k,v=kv.split(":",1)
                h[k.strip()]=v.strip()
    method=method.upper()
    v=not allow_insecure
    try:
        f=getattr(requests,method.lower(),None)
        if not f:
            return{"output":"","error":f"Unsupported method: {method}","success":False,"exit_code":1}
        if data and method in["POST","PUT","PATCH"]:
            r=f(url,data=data,headers=h,timeout=timeout,verify=v)
        else:
            r=f(url,headers=h,timeout=timeout,verify=v)
        s=f"{method} {url} -> Status: {r.status_code}"
        return{"output":s,"error":"","success":True,"exit_code":0,"method":method,"url":url,"status_code":r.status_code,"response_body":r.text,"response_headers":dict(r.headers)}
    except requests.exceptions.RequestException as e:
        return{"output":"","error":f"HTTP request error: {str(e)}","success":False,"exit_code":1}
