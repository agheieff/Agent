from openai import OpenAI
import logging
from typing import Dict, Optional, List, Any
from .base import BaseLLMClient, ModelInfo

logger = logging.getLogger(__name__)

class OpenAIClient(BaseLLMClient):
    def __init__(self,api_key:str,model:Optional[str]=None):
        self.requested_model=model
        super().__init__(api_key)

    def _initialize_client(self,api_key:str)->None:
        try:
            self.client=OpenAI(api_key=api_key)
            logger.info("OpenAI client initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing OpenAI client: {str(e)}",exc_info=True)
            raise ValueError(f"Failed to initialize OpenAI client: {str(e)}")

    def _register_models(self)->None:
        a1=ModelInfo("GPT-4.5 Preview","gpt-4.5-preview",True,True,128000,75.0,150.0,37.5,75.0)
        a2=ModelInfo("GPT-4o","gpt-4o",True,True,128000,2.5,10.0,1.25,2.5)
        a3=ModelInfo("o1","o1",True,True,128000,15.0,60.0,7.5,15.0)
        a4=ModelInfo("o3-mini","o3-mini",True,True,128000,1.1,4.4,0.55,1.1)
        self.models["gpt-4.5-preview"]=a1
        self.models["gpt-4o"]=a2
        self.models["o1"]=a3
        self.models["o3-mini"]=a4
        if self.requested_model and self.requested_model in self.models:
            self.default_model=self.requested_model
        else:
            self.default_model="o1"

    async def _make_api_call(self,m:List[Dict],mn:str,temperature:float,max_tokens:int,tool_usage:bool)->Any:
        if not hasattr(self,"client"):
            raise ValueError("OpenAI client not initialized")
        d={"model":mn,"messages":m,"max_tokens":max_tokens,"temperature":temperature}
        logger.debug(f"Sending request to OpenAI with {len(m)} messages")
        return self.client.chat.completions.create(**d)

    def extract_response_content(self,message)->str:
        r=super().extract_response_content(message)
        try:
            if hasattr(message,"choices")and message.choices and len(message.choices)>0 and hasattr(message.choices[0],"message"):
                c=message.choices[0]
                if hasattr(c.message,"tool_calls")and c.message.tool_calls and len(c.message.tool_calls)>0:
                    t=c.message.tool_calls[0]
                    if hasattr(t,"function"):
                        j={"name":t.function.name,"arguments":t.function.arguments,"response":r}
                        return __import__("json").dumps(j)
        except Exception as e:
            logger.error(f"Error extracting OpenAI response content: {e}")
            return f"Error parsing response: {e}"
        return r
