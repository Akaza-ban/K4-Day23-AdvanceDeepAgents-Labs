"""PROVIDED - do not edit. Builds the chat model from environment variables (see .env.example).

Each student brings their OWN API key and provider. Two ways (the first that matches wins):

1. Any OpenAI-compatible endpoint (OpenRouter, Together, Groq, a local Ollama or vLLM server, ...):
   LAB_BASE_URL=<endpoint url>   LAB_MODEL=<model name>   LAB_API_KEY=<key, may be empty for a local server>
   The names OPENAI_ENDPOINT / OPENAI_KEY / OPENAI_DEPLOYMENT_MODEL are accepted as aliases of the three above.
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


def _env(*names):
    """First non-empty environment variable among `names` (stripped), else None."""
    for name in names:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return None


def make_model():
    """Return a chat model configured from the environment."""
    name = _env("LAB_MODEL", "OPENAI_DEPLOYMENT_MODEL")
    if not name:
        raise RuntimeError(HELP)
    # Only send a temperature when asked: some reasoning models reject any non-default value.
    temperature = _env("LAB_TEMPERATURE")
    options = {"temperature": float(temperature)} if temperature is not None else {}
    base_url = _env("LAB_BASE_URL", "OPENAI_ENDPOINT")
    if base_url:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(base_url=base_url, api_key=_env("LAB_API_KEY", "OPENAI_KEY") or "not-needed", model=name,
                          timeout=120, **options)
    return init_chat_model(name, **options)
