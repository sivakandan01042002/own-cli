from typing import Literal, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from app.core.config import settings


def get_llm(
    provider: Optional[Literal["groq", "gemini"]] = None,
    model_name: Optional[str] = None,
    temperature: float = 0.0
) -> BaseChatModel:
    """
    Factory function to initialize and return a LangChain chat model.
    Supports Groq and Google Gemini based on settings and parameters.
    """
    selected_provider = provider or settings.DEFAULT_PROVIDER

    if selected_provider == "groq":
        from langchain_groq import ChatGroq
        model = model_name or settings.GROQ_MODEL
        return ChatGroq(
            model=model,
            api_key=settings.GROQ_API_KEY,
            temperature=temperature
        )
    elif selected_provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        model = model_name or settings.GEMINI_MODEL
        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=settings.GEMINI_API_KEY,
            temperature=temperature
        )
    else:
        raise ValueError(f"Unsupported LLM provider: {selected_provider}. Choose 'groq' or 'gemini'.")
