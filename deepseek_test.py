# test_deepseek.py
import os
from openai import OpenAI
from dotenv import load_dotenv

def test_deepseek():
    load_dotenv()
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("Error: DEEPSEEK_API_KEY not found in environment")
        return

    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com/v1"
        )

        print("Testing DeepSeek API connection...")
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "user", "content": "Hello, are you working?"}
            ],
            max_tokens=100
        )
        print("\nResponse:", response.choices[0].message.content)
        
    except Exception as e:
        print("\nError:", str(e))
        print("\nError type:", type(e).__name__)

if __name__ == "__main__":
    test_deepseek()# test_deepseek.py
import os
from openai import OpenAI
from dotenv import load_dotenv

def test_deepseek():
    load_dotenv()
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("Error: DEEPSEEK_API_KEY not found in environment")
        return

    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com/v1"
        )

        print("Testing DeepSeek API connection...")
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "user", "content": "Hello, are you working?"}
            ],
            max_tokens=100
        )
        print("\nResponse:", response.choices[0].message.content)
        
    except Exception as e:
        print("\nError:", str(e))
        print("\nError type:", type(e).__name__)

if __name__ == "__main__":
    test_deepseek()# test_deepseek.py
import os
from openai import OpenAI
from dotenv import load_dotenv

def test_deepseek():
    load_dotenv()
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("Error: DEEPSEEK_API_KEY not found in environment")
        return

    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com/v1"
        )

        print("Testing DeepSeek API connection...")
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "user", "content": "Hello, are you working?"}
            ],
            max_tokens=100
        )
        print("\nResponse:", response.choices[0].message.content)
        
    except Exception as e:
        print("\nError:", str(e))
        print("\nError type:", type(e).__name__)

if __name__ == "__main__":
    test_deepseek()# test_deepseek.py
import os
from openai import OpenAI
from dotenv import load_dotenv

def test_deepseek():
    load_dotenv()
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("Error: DEEPSEEK_API_KEY not found in environment")
        return

    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com/v1"
        )

        print("Testing DeepSeek API connection...")
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "user", "content": "Hello, are you working?"}
            ],
            max_tokens=100
        )
        print("\nResponse:", response.choices[0].message.content)
        
    except Exception as e:
        print("\nError:", str(e))
        print("\nError type:", type(e).__name__)

if __name__ == "__main__":
    test_deepseek()
