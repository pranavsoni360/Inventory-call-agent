import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

model = genai.GenerativeModel("gemini-2.5-flash-native-audio-latest")

response = model.generate_content("Say hello like a polite phone assistant")

print(response.text)
