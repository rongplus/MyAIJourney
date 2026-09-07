from openai import OpenAI
MODEL = "llama2"
openai = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

def openAIChat(prompt):
    response = openai.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

