from abc import ABC,abstractmethod
from typing import Dict,Any,Optional,List,Tuple
import logging
import inspect

try:
    from Output.output_manager import output_manager
except:
    output_manager=None

logger=logging.getLogger(__name__)

class ToolHandler(ABC):
    name:str=""
    description:str=""
    usage:str=""
    examples:List[Tuple[str,str]]=[]
    formatter:str="default"
    test_mode_allowed:bool=False
    internet_tool:bool=False

    @abstractmethod
    async def execute(self,**kwargs)->Dict[str,Any]:
        pass

    async def run(self,**kwargs)->Dict[str,Any]:
        try:
            r=await self.execute(**kwargs)
            r["tool_name"]=self.name
            e=r.get("exit_code",0)
            r["exit_code"]=e
            c=r.get("output","")if e==0 else r.get("error","")
            r["result"]=c
            r.pop("success",None)
            if output_manager is not None:
                await output_manager.handle_tool_output(self.name,r)
            return r
        except Exception as e:
            logger.exception(f"Error {self.name}: {e}")
            rr={"tool_name":self.name,"result":str(e),"exit_code":1}
            if output_manager:
                await output_manager.handle_tool_output(self.name,rr)
            return rr

    @classmethod
    def get_metadata(cls)->Dict[str,Any]:
        return{"name":cls.name or cls.__name__.lower(),"description":cls.description,"usage":cls.usage,"examples":cls.examples,"formatter":cls.formatter,"test_mode_allowed":getattr(cls,"test_mode_allowed",False),"internet_tool":getattr(cls,"internet_tool",False),"docstring":cls.__doc__or""}

class FileTool(ToolHandler):
    pass

class NetworkTool(ToolHandler):
    pass

class SystemTool(ToolHandler):
    pass
