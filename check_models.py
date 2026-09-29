import os
os.chdir(r'c:\Users\raghi\OneDrive\Desktop\Decision_Graveyard_agent')
from dotenv import load_dotenv
load_dotenv()
from groq import Groq

g = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Test qwen
print("Testing qwen/qwen3.8-27b:")
try:
    r = g.chat.completions.create(
        model="qwen/qwen3.8-27b",
        messages=[{"role": "user", "content": 'Reply with exactly this JSON and nothing else: {"test": true}'}],
        temperature=0.0,
        max_tokens=30,
    )
    text = r.choices[0].message.content.strip()
    print("  response:", repr(text))
    print("  finish_reason:", r.choices[0].finish_reason)
except Exception as e:
    print("  ERROR:", e)

# Debug gpt-oss-120b — check finish reason and think tokens
print("\nDebugging openai/gpt-oss-120b:")
try:
    r2 = g.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": 'Say the word OK'}],
        temperature=0.0,
        max_tokens=50,
    )
    c = r2.choices[0]
    print("  content:", repr(c.message.content))
    print("  finish_reason:", c.finish_reason)
    # Check if there are reasoning tokens
    if hasattr(r2, 'usage'):
        print("  usage:", r2.usage)
    # Check raw choice
    print("  raw choice keys:", dir(c.message))
except Exception as e:
    print("  ERROR:", e)
