"""PROVIDED - do not edit. Builds the chat model from environment variables (see .env.example).

Each student brings their OWN API key and provider. Two ways (the first that matches wins):

1. Any OpenAI-compatible endpoint (OpenRouter, Together, Groq, a local Ollama or vLLM server, ...):
   LAB_BASE_URL=<endpoint url>   LAB_MODEL=<model name>   LAB_API_KEY=<key, may be empty for a local server>
2. Any LangChain provider: LAB_MODEL="<provider>:<model name>" plus the key variable that provider expects,
   for example  openai:<model>  (OPENAI_API_KEY),  anthropic:<model>  (ANTHROPIC_API_KEY),
   google_genai:<model>  (GOOGLE_API_KEY).

The model MUST support tool calling. Model names change over time: copy them from your provider's documentation.
"""
import os

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

load_dotenv()

HELP = (
    "No model configured. Copy .env.example to .env and set LAB_MODEL "
    "(for example LAB_MODEL=openai:<model name> and OPENAI_API_KEY=...), "
    "or LAB_BASE_URL + LAB_MODEL + LAB_API_KEY for an OpenAI-compatible endpoint."
)


def make_model():
    """Return a chat model configured from the environment."""
    name = os.getenv("LAB_MODEL")
    if not name:
        raise RuntimeError(HELP)
    temperature = float(os.getenv("LAB_TEMPERATURE", "0"))
    base_url = os.getenv("LAB_BASE_URL")
    if base_url:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(base_url=base_url, api_key=os.getenv("LAB_API_KEY") or "not-needed", model=name,
                          temperature=temperature, timeout=120)
    return init_chat_model(name, temperature=temperature)
