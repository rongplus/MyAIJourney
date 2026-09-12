# local url
from url_client import list_models, respond_url, chat_stream

from localChatOllama import localChatOllama
from localOpenAI import localOpenAIClient

def get_default_model(models: list[str]):
    if not models:
        return None
    return "qwen2.5:7b" if "qwen2.5:7b" in models else models[0]


def getLocalOllamaClient(modelName: str, temperature: float,memory_file: str,custom_tools: list[str]):
    return localChatOllama(modelName=modelName, temperature=temperature, memory_file=memory_file, custom_tools=custom_tools)


def getLocalOpenAIClient(modelName: str, temperature: float,memory_file: str,custom_tools: list[str]):    
    return localOpenAIClient(modelName=modelName, temperature=temperature, memory_file=memory_file, custom_tools=custom_tools)


def getClient(special:str, modelName: str, temperature: float, memory_file: str,custom_tools: list[str]):
    if special == "OpenAI":
        return getLocalOpenAIClient(modelName=modelName, temperature=temperature,memory_file="Default_memory.json",custom_tools=custom_tools)
    return getLocalOllamaClient(modelName=modelName, temperature=temperature,memory_file="Default_memory.json",custom_tools=custom_tools)