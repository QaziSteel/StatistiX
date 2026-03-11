import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

print("--- Testing Every Model in List ---")
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            m_name = m.name # This is usually 'models/...'
            print(f"\nTesting: {m_name}")
            try:
                model = genai.GenerativeModel(m_name)
                resp = model.generate_content("Hi", generation_config=genai.types.GenerationConfig(max_output_tokens=10))
                print(f"SUCCESS: {resp.text.strip()}")
            except Exception as e:
                print(f"FAILED: {e}")
except Exception as e:
    print(f"Error listing models: {e}")
