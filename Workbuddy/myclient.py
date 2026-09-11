# local url
from url_client import list_models, respond_url, chat_stream

from localChatOllama import localChatOllama
from localOpenAI import localOpenAIClient

def get_default_model(models: list[str]):
    if not models:
        return None
    return "qwen2.5:7b" if "qwen2.5:7b" in models else models[0]


def getLocalOllamaClient(modelName: str, temperature: float):
    return localChatOllama(modelName=modelName, temperature=temperature)


def getLocalOpenAIClient(modelName: str, temperature: float):    
    return localOpenAIClient(modelName=modelName, temperature=temperature, memory_file="open AI_memory.json")
# local openai