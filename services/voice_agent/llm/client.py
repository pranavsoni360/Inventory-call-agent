import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("GEMINI_API_KEY"))

def ask_llm(prompt):
    response = client.chat.completions.create(
        model="gemini-2.5-flash-native-audio-latest",
        messages=[
            {"role": "system", "content": "You are a helpful phone agent."},
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content
