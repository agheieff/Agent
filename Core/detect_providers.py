import os
import glob
import json

def get_available_providers(clients_dir='Clients'):
    s=set()
    p=os.path.join(clients_dir,'*.py')
    for f in glob.glob(p):
        b=os.path.basename(f)
        if b=='__init__.py':
            continue
        n=b.replace('.py','').lower()
        s.add(n)
    return s

def get_available_api_keys():
    d={'openai':'OPENAI_API_KEY','anthropic':'ANTHROPIC_API_KEY','deepseek':'DEEPSEEK_API_KEY'}
    r={}
    for k,v in d.items():
        x=os.getenv(v)
        if x:
            r[k]=x
    return r

def get_active_providers(clients_dir='Clients'):
    a=get_available_providers(clients_dir)
    b=get_available_api_keys()
    c={}
    for p in a:
        if p in b:
            c[p]=b[p]
    return c

if __name__=='__main__':
    x=get_active_providers()
    print("Active providers:")
    print(json.dumps(x,indent=4))
