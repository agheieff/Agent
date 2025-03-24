#!/usr/bin/env python3
import os
import sys
from Clients.API.openai import OpenAIClient
from Clients.API.anthropic import AnthropicClient
from Clients.base import Message

def test_openai():
    client = OpenAIClient()
    
    print(f"Available models: {client.get_available_models()}")
    print(f"Default model: {client.default_model}")
    
    messages = [
        Message(role="user", content="Hello, who are you?")
    ]
    
    try:
        response = client.chat_completion(
            messages=messages,
            model="gpt-4o",
            temperature=0.7
        )
        
        print("Response:", response.choices[0].message.content)
    except Exception as e:
        print(f"Error: {e}")

def test_anthropic():
    client = AnthropicClient()
    
    print(f"Available models: {client.get_available_models()}")
    print(f"Default model: {client.default_model}")
    
    messages = [
        Message(role="user", content="Hello, who are you?")
    ]
    
    try:
        response = client.chat_completion(
            messages=messages,
            model="claude-3-haiku",
            temperature=0.7
        )
        
        print("Response:", response.content[0].text)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("Testing OpenAI client:")
    test_openai()
    
    print("\nTesting Anthropic client:")
    test_anthropic() 