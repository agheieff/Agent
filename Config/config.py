import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger=logging.getLogger(__name__)

class Config:
    def __init__(self,config_path:Optional[Path]=None):
        self._config:Dict[str,Any]={}
        self._config_path=config_path or self._find_config_file()
        self._load_config()

    def _find_config_file(self)->Path:
        if os.environ.get("ARCADIA_CONFIG_PATH"):
            e=Path(os.environ["ARCADIA_CONFIG_PATH"])
            if e.exists():
                return e
        s=[Path.cwd()/"Config"/"config.yaml",Path.cwd()/"config.yaml",Path.home()/".arcadia"/"config.yaml",Path(__file__).parent/"config.yaml"]
        for p in s:
            if p.exists():
                return p
        return Path(__file__).parent/"config.yaml"

    def _load_config(self):
        self._config=self._load_default_config()
        if self._config_path.exists():
            try:
                with open(self._config_path,"r")as f:
                    c=yaml.safe_load(f)
                    if c:
                        self._update_dict_recursive(self._config,c)
            except Exception as e:
                logger.error(f"Error loading config from {self._config_path}: {e}")
        self._apply_environment_variables()

    def _load_default_config(self)->Dict[str,Any]:
        d=Path(__file__).parent/"defaults.yaml"
        if d.exists():
            try:
                with open(d,"r")as f:
                    return yaml.safe_load(f)or{}
            except Exception as e:
                logger.error(f"Error loading default config: {e}")
        return{"agent":{"test_mode":False}}

    def _update_dict_recursive(self,t:Dict,s:Dict):
        for k,v in s.items():
            if k in t and isinstance(t[k],dict)and isinstance(v,dict):
                self._update_dict_recursive(t[k],v)
            else:
                t[k]=v

    def _apply_environment_variables(self):
        p="ARCADIA_"
        for k,v in os.environ.items():
            if k.startswith(p):
                c=k[len(p):].lower().replace("_",".")
                self.set(c,v)

    def get(self,path:str,default:Any=None)->Any:
        ps=path.split(".")
        x=self._config
        try:
            for p in ps:
                x=x[p]
            return x
        except:
            return default

    def set(self,path:str,value:Any):
        ps=path.split(".")
        x=self._config
        for p in ps[:-1]:
            if p not in x:
                x[p]={}
            x=x[p]
        if isinstance(value,str):
            if value.lower()in("true","yes","y","1"):
                value=True
            elif value.lower()in("false","no","n","0"):
                value=False
            elif value.isdigit():
                value=int(value)
        x[ps[-1]]=value

    def save(self,path:Optional[Path]=None):
        p=path or self._config_path
        try:
            p.parent.mkdir(parents=True,exist_ok=True)
            with open(p,"w")as f:
                yaml.dump(self._config,f,default_flow_style=False)
            logger.info(f"Configuration saved to {p}")
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")

    def is_test_mode(self)->bool:
        return self.get("agent.test_mode",False)

    def to_dict(self)->Dict[str,Any]:
        return self._config.copy()

config=Config()

def get_test_mode()->bool:
    return config.is_test_mode()
