def generate_command_execution_guide(p:str="openai")->str:
    p=p.lower()
    if p=="anthropic":
        return"""
tool_use:{
"name":"tool_name","input":{"param1":"value1"}}
"""
    elif p=="deepseek":
        return"""
{
"thinking":"hidden reasoning","reasoning":"explanation","action":"tool_name","action_input":{"param":"value"},"response":"text"
}
"""
    return"""
{
"thinking":"hidden reasoning","analysis":"explanation","tool_calls":[{"name":"tool_name","params":{"param":"value"}}],"answer":"text"
}
"""

def generate_agent_role_explanation()->str:
    return"Agent operates autonomously."

def generate_conversation_tracking()->str:
    return"Use compact or finish when needed."

def generate_system_prompt(config_path=None,summary_path=None)->str:
    s=generate_command_execution_guide()+"\n"+generate_agent_role_explanation()+"\n"+generate_conversation_tracking()
    return s
