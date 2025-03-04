import logging
from typing import Optional, List, Dict, Any
from openai import OpenAI
from .base import BaseLLMClient, ModelInfo

logger = logging.getLogger(__name__)

class DeepSeekClient(BaseLLMClient):
    def __init__(self,api_key:str):
        super().__init__(api_key,False)

    def _initialize_client(self,api_key:str)->None:
        try:
            self.client=OpenAI(api_key=api_key,base_url="https://api.deepseek.com")
            logger.info("DeepSeek client initialized successfully")
        except Exception as e:
            raise ValueError(f"Failed to initialize DeepSeek client: {e}")

    def _register_models(self)->None:
        self.models["deepseek-reasoner"]=ModelInfo("DeepSeek Reasoner","deepseek-reasoner",False,False,128000,0.14,2.19,0.05,0.14,(16,30,0,30),0.75)
        self.default_model="deepseek-reasoner"

    async def _make_api_call(self,m:List[Dict],mn:str,temperature:float,max_tokens:int,tool_usage:bool)->Any:
        if not hasattr(self,"client"):
            raise ValueError("DeepSeek client not initialized")
        d={"model":mn,"messages":m,"max_tokens":max_tokens,"temperature":temperature}
        logger.debug(f"Sending request to DeepSeek with {len(m)} messages")
        return self.client.chat.completions.create(**d)

    def extract_response_content(self,message)->str:
        r=super().extract_response_content(message)
        try:
            if hasattr(message,"choices")and message.choices:
                c=message.choices[0]
                fc=getattr(c.message,"function_call",None)
                if fc:
                    j={"action":fc.name,"action_input":fc.arguments,"response":r}
                    return __import__("json").dumps(j)
        except Exception as e:
            logger.error(f"Error extracting DeepSeek response content: {e}")
            return f"Error parsing response: {e}"
        return r
