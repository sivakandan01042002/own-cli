import logging
import warnings
from typing import Literal, Optional, Sequence, Dict, Tuple
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool

# Suppress AFC and Google GenAI library log notices
logging.getLogger("google.genai").setLevel(logging.ERROR)
logging.getLogger("google.genai.models").setLevel(logging.ERROR)
logging.getLogger("google").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message=".*Automatic Function Calling.*")
warnings.filterwarnings("ignore", message=".*AFC.*")
warnings.filterwarnings("ignore", category=UserWarning, module="langchain_google_genai")

try:
    from google.genai.models import Models, AsyncModels
    Models._logged_afc_warning = True
    AsyncModels._logged_afc_warning = True
except Exception:
    pass

from app.core.config import settings

# Global in-memory cache for LLM instances & tool-bound clients
_LLM_CACHE: Dict[Tuple[str, Optional[str], float], BaseChatModel] = {}
_CODER_LLM_CACHE: Dict[str, BaseChatModel] = {}


def get_llm(
    provider: Optional[Literal["groq", "gemini"]] = None,
    model_name: Optional[str] = None,
    temperature: float = 0.0,
) -> BaseChatModel:
    """
    Factory function to initialize a new LangChain chat model.
    """
    from app.core.user_config import get_active_provider, get_active_model_name
    selected_provider = provider or get_active_provider()

    if selected_provider == "groq":
        from langchain_groq import ChatGroq
        model = model_name or get_active_model_name() or settings.GROQ_MODEL
        return ChatGroq(
            model=model,
            api_key=settings.GROQ_API_KEY,
            temperature=temperature,
        )
    elif selected_provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        model = model_name or get_active_model_name() or settings.GEMINI_MODEL
        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=settings.GEMINI_API_KEY,
            temperature=temperature,
        )
    else:
        raise ValueError(f"Unsupported LLM provider: {selected_provider}. Choose 'groq' or 'gemini'.")


def get_cached_llm(
    provider: Optional[Literal["groq", "gemini"]] = None,
    model_name: Optional[str] = None,
    temperature: float = 0.0,
) -> BaseChatModel:
    """
    Returns a cached singleton LLM instance to avoid repeated object initialization.
    Dynamically switches when provider or model changes.
    """
    from app.core.user_config import get_active_provider, get_active_model_name
    selected_provider = provider or get_active_provider()
    selected_model = model_name or get_active_model_name()
    cache_key = (selected_provider, selected_model, temperature)

    if cache_key not in _LLM_CACHE:
        _LLM_CACHE[cache_key] = get_llm(
            provider=selected_provider,
            model_name=selected_model,
            temperature=temperature,
        )
    return _LLM_CACHE[cache_key]


def get_cached_coder_llm(tools: Optional[Sequence[BaseTool]] = None) -> BaseChatModel:
    """
    Returns a cached singleton LLM with tools pre-bound, avoiding repeated tool binding.
    """
    from app.integrations.tools import ALL_TOOLS
    from app.core.user_config import get_active_provider, get_active_model_name
    bound_tools = tools if tools is not None else ALL_TOOLS

    selected_provider = get_active_provider()
    selected_model = get_active_model_name()
    cache_key = f"{selected_provider}:{selected_model}"

    if cache_key not in _CODER_LLM_CACHE:
        base = get_cached_llm(provider=selected_provider, model_name=selected_model)
        _CODER_LLM_CACHE[cache_key] = base.bind_tools(bound_tools)
    return _CODER_LLM_CACHE[cache_key]
