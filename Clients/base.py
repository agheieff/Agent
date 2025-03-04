from abc import ABC, abstractmethod
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

class ModelInfo:
    def __init__(self,name:str,api_name:str,supports_reasoning:bool=True,prefers_separate_system_prompt:bool=True,context_window:int=128000,input_price:float=0.0,output_price:float=0.0,input_cache_read_price:Optional[float]=None,input_cache_write_price:Optional[float]=None,discount_hours:Optional[Tuple[int,int,int,int]]=None,discount_rate:float=0.0):
        self.name=name
        self.api_name=api_name
        self.supports_reasoning=supports_reasoning
        self.prefers_separate_system_prompt=prefers_separate_system_prompt
        self.context_window=context_window
        self.input_price=input_price
        self.output_price=output_price
        self.input_cache_read_price=input_cache_read_price or input_price*0.1
        self.input_cache_write_price=input_cache_write_price or input_price*1.25
        self.discount_hours=discount_hours
        self.discount_rate=discount_rate

    def get_pricing(self)->Dict[str,float]:
        p={"input":self.input_price/1000000,"output":self.output_price/1000000}
        if self.input_cache_read_price is not None:
            p["input_cache_read"]=self.input_cache_read_price/1000000
        if self.input_cache_write_price is not None:
            p["input_cache_write"]=self.input_cache_write_price/1000000
        if self.discount_hours and self.discount_rate>0:
            now=datetime.now()
            cm=now.hour*60+now.minute
            sh,sm,eh,em=self.discount_hours
            smn=sh*60+sm
            emn=eh*60+em
            d=False
            if emn<smn:
                if cm>=smn or cm<=emn:
                    d=True
            else:
                if cm>=smn and cm<=emn:
                    d=True
            if d:
                r=1.0-self.discount_rate
                for k in p:
                    p[k]*=r
        return p

class TokenUsage:
    def __init__(self,prompt_tokens=0,completion_tokens=0,total_tokens=0,model="",timestamp=None):
        self.prompt_tokens=prompt_tokens
        self.completion_tokens=completion_tokens
        self.total_tokens=total_tokens
        self.model=model
        self.timestamp=timestamp or datetime.now()
    def to_dict(self)->Dict[str,Any]:
        return{"prompt_tokens":self.prompt_tokens,"completion_tokens":self.completion_tokens,"total_tokens":self.total_tokens,"model":self.model,"timestamp":self.timestamp.isoformat()}

class BaseLLMClient(ABC):
    def __init__(self,api_key:str="",use_system_prompt:bool=True):
        if api_key and api_key.startswith("sk-")and len(api_key)<20:
            logger.warning("API key has unexpected format or length")
        self.usage_history:List[TokenUsage]=[]
        self.total_prompt_tokens=0
        self.total_completion_tokens=0
        self.total_tokens=0
        self.models:Dict[str,ModelInfo]={}
        self.default_model=None
        self.use_system_prompt=use_system_prompt
        self._initialize_client(api_key)
        self._register_models()

    def get_model_info(self,model_name:str)->Optional[ModelInfo]:
        if model_name in self.models:
            return self.models[model_name]
        for m in self.models.values():
            if m.api_name==model_name:
                return m
        return None

    def get_available_models(self)->List[str]:
        return list(self.models.keys())

    def add_usage(self,u:TokenUsage):
        self.usage_history.append(u)
        self.total_prompt_tokens+=u.prompt_tokens
        self.total_completion_tokens+=u.completion_tokens
        self.total_tokens+=u.total_tokens

    def get_usage_summary(self)->Dict[str,Any]:
        return{"total_prompt_tokens":self.total_prompt_tokens,"total_completion_tokens":self.total_completion_tokens,"total_tokens":self.total_tokens,"calls":len(self.usage_history),"history":[x.to_dict()for x in self.usage_history]}

    def adjust_prompts(self,system_prompt:Optional[str],user_prompt:str)->Tuple[Optional[str],str]:
        if not self.use_system_prompt and system_prompt:
            c=system_prompt+"\n\n"+user_prompt
            return(None,c)
        return(system_prompt,user_prompt)

    @abstractmethod
    def _initialize_client(self,api_key:str)->None:
        pass

    @abstractmethod
    def _register_models(self)->None:
        pass

    def extract_response_content(self,message)->str:
        try:
            if hasattr(message,"content"):
                if isinstance(message.content,list):
                    t=[]
                    for b in message.content:
                        if isinstance(b,dict)and b.get("type")=="text"and"text"in b:
                            t.append(b["text"])
                        elif hasattr(b,"text"):
                            t.append(b.text)
                    if t:
                        return"\n".join(t)
                    if message.content:
                        f=message.content[0]
                        return f.text if hasattr(f,"text")else f.get("text","")
                elif isinstance(message.content,str):
                    return message.content
            elif hasattr(message,"completion"):
                return message.completion
            elif hasattr(message,"choices")and message.choices:
                f=message.choices[0]
                if hasattr(f,"message")and hasattr(f.message,"content"):
                    return f.message.content
            return str(message)
        except Exception as e:
            logger.error(f"Error extracting response content: {e}")
            return f"Error parsing response: {e}"

    def track_usage(self,message,model_name:str):
        d=self.extract_usage_data(message,model_name)
        u=TokenUsage(d["prompt_tokens"],d["completion_tokens"],d["total_tokens"],model_name)
        self.add_usage(u)

    def extract_usage_data(self,message,model_name:str)->Dict[str,int]:
        r=None
        try:
            if hasattr(message,"usage"):
                if hasattr(message.usage,"input_tokens")and hasattr(message.usage,"output_tokens"):
                    r={"prompt_tokens":message.usage.input_tokens,"completion_tokens":message.usage.output_tokens,"total_tokens":message.usage.input_tokens+message.usage.output_tokens}
                elif hasattr(message.usage,"prompt_tokens")and hasattr(message.usage,"completion_tokens"):
                    r={"prompt_tokens":message.usage.prompt_tokens,"completion_tokens":message.usage.completion_tokens,"total_tokens":message.usage.total_tokens}
                elif isinstance(message.usage,dict):
                    r={"prompt_tokens":message.usage.get("prompt_tokens",0),"completion_tokens":message.usage.get("completion_tokens",0),"total_tokens":message.usage.get("total_tokens",0)}
            if not r:
                logger.warning("Token usage not available from API, using estimation")
                x=self.extract_response_content(message)
                p=10
                if isinstance(message,list):
                    p=sum(len(m.get("content","").split())for m in message)
                c=len(x.split())
                r={"prompt_tokens":p,"completion_tokens":c,"total_tokens":p+c}
        except Exception as e:
            logger.warning(f"Error calculating token usage: {e}")
            r={"prompt_tokens":10,"completion_tokens":10,"total_tokens":20}
        return r

    async def generate_response(self,h:List[Dict])->str:
        try:
            i=self.get_model_info(self.default_model)
            if i and not i.prefers_separate_system_prompt:
                c="\n".join(m.get("content","")for m in h)
                if not c.strip():
                    c="Hello, please respond."
                h=[{"role":"user","content":c.strip()}]
            r=await self.get_response(None,None,h,0.5,i.context_window if i else 4096,False,self.default_model)
            if r is None:
                return"I encountered an error generating a response. Please try again."
            return r
        except Exception as e:
            logger.error(f"Error in generate_response: {e}")
            return f"I encountered an error generating a response: {e}"

    async def get_response(self,p:Optional[str],s:Optional[str],h:List[Dict]=None,temperature:float=0.5,max_tokens:int=4096,tool_usage:bool=False,model:Optional[str]=None)->Optional[str]:
        try:
            mn=model or self.default_model
            mi=self.get_model_info(mn)
            msgs=h or[]
            if not msgs:
                if s and(not mi or mi.prefers_separate_system_prompt):
                    msgs.append({"role":"system","content":s})
                    if p:
                        msgs.append({"role":"user","content":p})
                else:
                    c=(s+"\n\n"+p)if(s and p)else(s or p or"")
                    if c:
                        msgs.append({"role":"user","content":c})
            an=mi.api_name if mi else mn
            rr=await self._make_api_call(msgs,an,temperature,max_tokens,tool_usage)
            self.track_usage(rr,an)
            return self.extract_response_content(rr)
        except Exception as e:
            logger.error(f"API call failed: {e}")
            return None

    @abstractmethod
    async def _make_api_call(self,msgs:List[Dict],model_name:str,temperature:float,max_tokens:int,tool_usage:bool)->Any:
        pass
