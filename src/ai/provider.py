from ai import ollama_provider
from ai import openai_provider


def create_provider(provider_name, api_key=None):
    provider_name = provider_name.lower()

    if provider_name == "ollama":
        client = ollama_provider.create_client()

        return {
            "name": "ollama",
            "module": ollama_provider,
            "client": client,
            "state": None
        }

    if provider_name == "openai":
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required when using the OpenAI provider.")

        client = openai_provider.create_client(api_key)

        return {
            "name": "openai",
            "module": openai_provider,
            "client": client,
            "state": None
        }

    raise ValueError(f"Unknown AI provider: {provider_name}")