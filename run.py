import asyncio
import os
import sys
import argparse
import logging
from pathlib import Path
from dotenv import load_dotenv
import signal
import json
from Config import config
from Clients import get_llm_client

logger=logging.getLogger(__name__)
INITIAL_PROMPT_HISTORY_FILE='~/.agent_prompt_history'
CONTEXT_HISTORY_FILE='~/.agent_context_history'
PROVIDER_ENV_PREFIXES={"anthropic":"ANTHROPIC","deepseek":"DEEPSEEK","openai":"OPENAI"}
CLIENT_CLASSES={"anthropic":"AnthropicClient","deepseek":"DeepSeekClient","openai":"OpenAIClient"}
current_agent=None
paused_for_context=False

def handle_pause_signal(signum,frame):
    global current_agent,paused_for_context
    if current_agent and not paused_for_context:
        paused_for_context=True
        asyncio.create_task(pause_for_context_input())

async def pause_for_context_input():
    global current_agent,paused_for_context
    print("\n============================================================")
    print("AGENT PAUSED FOR ADDITIONAL CONTEXT")
    print("------------------------------------------------------------")
    try:
        import readline
        h=os.path.expanduser(CONTEXT_HISTORY_FILE)
        try:
            readline.read_history_file(h)
            readline.set_history_length(1000)
        except:
            pass
        import atexit
        if not hasattr(pause_for_context_input,"_readline_initialized"):
            atexit.register(readline.write_history_file,h)
            pause_for_context_input._readline_initialized=True
    except:
        pass
    lines=[]
    while True:
        try:
            line=input("[Message] > ")
            if not line.strip():
                break
            lines.append(line)
        except EOFError:
            break
    additional_context="\n".join(lines)
    if additional_context.strip():
        if hasattr(current_agent,"local_conversation_history"):
            current_agent.local_conversation_history.append({"role":"user","content":additional_context})
        print("Context added.")
    else:
        print("No additional context.")
    paused_for_context=False

def get_initial_prompt()->str:
    try:
        import readline
        h=os.path.expanduser(INITIAL_PROMPT_HISTORY_FILE)
        try:
            readline.read_history_file(h)
            readline.set_history_length(1000)
        except:
            pass
        import atexit
        atexit.register(readline.write_history_file,h)
    except:
        pass
    print("Enter your prompt (blank line to finish):")
    lines=[]
    while True:
        try:
            line=input()
            if not line.strip():
                break
            lines.append(line)
        except EOFError:
            break
    return"\n".join(lines)

def get_available_model_providers()->dict:
    r={}
    import importlib
    for pv,envp in PROVIDER_ENV_PREFIXES.items():
        k=os.getenv(f"{envp}_API_KEY","").strip()
        if not k:
            continue
        try:
            mod=importlib.import_module(f"Clients.{pv}")
            c=getattr(mod,CLIENT_CLASSES[pv])
            cl=c(k)
            m=cl.get_available_models()
            r[pv]={"env_prefix":envp,"models":m}
        except Exception as e:
            logger.warning(f"Error {pv}: {str(e)}")
    return r

def get_model_choice(ap:dict)->dict:
    if not ap:
        print("No providers found. Please set an API key.")
        sys.exit(1)
    if len(ap)==1:
        o=list(ap.keys())[0]
        om=ap[o]["models"][0]
        print(f"Using provider: {o}, model: {om}")
        return{"provider":o,"model":om}
    else:
        p=list(ap.keys())
        for i,a in enumerate(p,start=1):
            print(f"{i}. {a} (models: {ap[a]['models']})")
        try:
            c=int(input("Choose provider #: "))-1
            if c<0 or c>=len(p):
                raise ValueError
            chosen_provider=p[c]
        except:
            chosen_provider=p[0]
            print(f"Invalid choice, default: {chosen_provider}")
        ms=ap[chosen_provider]["models"]
        if len(ms)==1:
            return{"provider":chosen_provider,"model":ms[0]}
        else:
            for i,m in enumerate(ms,start=1):
                print(f"{i}. {m}")
            try:
                c2=int(input("Choose model #: "))-1
                if c2<0 or c2>=len(ms):
                    raise ValueError
                chosen_model=ms[c2]
            except:
                chosen_model=ms[0]
                print(f"Invalid model choice, default: {chosen_model}")
            return{"provider":chosen_provider,"model":chosen_model}

async def main():
    global current_agent
    load_dotenv()
    if hasattr(signal,"SIGTSTP"):
        signal.signal(signal.SIGTSTP,handle_pause_signal)
    parser=argparse.ArgumentParser()
    parser.add_argument("--test",action="store_true")
    parser.add_argument("--provider",choices=list(PROVIDER_ENV_PREFIXES.keys()))
    parser.add_argument("--model")
    parser.add_argument("--headless",action="store_true")
    parser.add_argument("--no-internet",action="store_true")
    parser.add_argument("--non-autonomous",action="store_true")
    parser.add_argument("--autonomous",action="store_true")
    args=parser.parse_args()
    if args.test:
        config.set("agent.test_mode",True)
    if args.headless:
        config.set("agent.headless",True)
    if args.no_internet:
        config.set("agent.allow_internet",False)
    if args.non_autonomous:
        config.set("agent.autonomous_mode",False)
    elif args.autonomous:
        config.set("agent.autonomous_mode",True)
    ap=get_available_model_providers()
    if args.provider:
        if args.provider not in ap:
            print(f"Provider {args.provider} not found or no API key set.")
            sys.exit(1)
        provider=args.provider
        if args.model:
            if args.model in ap[provider]["models"]:
                model=args.model
            else:
                print(f"Model {args.model} not found for {provider}.")
                print(f"Available: {','.join(ap[provider]['models'])}")
                model=ap[provider]["models"][0]
                print(f"Using: {model}")
        else:
            model=ap[provider]["models"][0]
    else:
        if not ap:
            print("No providers found. Please set an API key.")
            sys.exit(1)
        if args.model:
            guess=None
            for x in ap:
                if args.model in ap[x]["models"]:
                    guess=x
                    break
            if not guess:
                guess=list(ap.keys())[0]
                print(f"Model {args.model} not found. Using {guess}")
            provider=guess
            if args.model in ap[provider]["models"]:
                model=args.model
            else:
                model=ap[provider]["models"][0]
        else:
            c=get_model_choice(ap)
            provider=c["provider"]
            model=c["model"]
    ep=PROVIDER_ENV_PREFIXES.get(provider,provider.upper())
    ak=os.getenv(f"{ep}_API_KEY","").strip()
    if not ak:
        print(f"No API key for {provider}")
        sys.exit(1)
    if config.get("agent.headless",False):
        ip="Headless mode"
    else:
        ip=get_initial_prompt()
        if not ip.strip():
            print("Empty prompt.")
            sys.exit(0)
    print(f"Provider: {provider}, model: {model}")
    if config.get("agent.test_mode",False):
        print("TEST MODE enabled.")
    from Prompts.main import generate_system_prompt
    sp=generate_system_prompt()
    from Core.agent import AutonomousAgent
    a=AutonomousAgent(ak,model,provider,config.get("agent.test_mode",False),config.to_dict())
    current_agent=a
    s,u=a.llm.adjust_prompts(sp,ip)
    try:
        await a.run(u,s)
    except KeyboardInterrupt:
        print("Exiting.")
    finally:
        if a and hasattr(a,"llm")and getattr(a.llm,"usage_history",None):
            from Output.output_manager import output_manager
            usage_output={"success":True,"formatter":"api_usage_summary","total_cost":getattr(a.llm,"total_cost",0.0)}
            asyncio.run(output_manager.handle_tool_output("api_usage_summary",usage_output))
        print("Agent session ended.")

if __name__=="__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutdown")
        sys.exit(0)
    except(RuntimeError,IOError)as e:
        print(f"Fatal error: {str(e)}")
        sys.exit(1)
