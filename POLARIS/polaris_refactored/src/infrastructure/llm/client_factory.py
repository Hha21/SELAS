"""
LLM Client Factory

Provides factory functions for creating LLM clients based on provider configuration.
"""

from typing import Type, Dict
from .models import LLMConfiguration, LLMProvider
from .client import LLMClient, OpenAIClient, AnthropicClient, GoogleClient, MockLLMClient
from .exceptions import LLMConfigurationError


class LLMClientFactory:
    """Factory for creating LLM clients based on provider."""
    
    _CLIENT_REGISTRY: Dict[LLMProvider, Type[LLMClient]] = {
        LLMProvider.OPENAI: OpenAIClient,
        LLMProvider.ANTHROPIC: AnthropicClient,
        LLMProvider.GOOGLE: GoogleClient,
        LLMProvider.MOCK: MockLLMClient,
        # LOCAL provider would need a custom implementation
    }
    
    @classmethod
    def create_client(cls, config: LLMConfiguration) -> LLMClient:
        """
        Create an LLM client based on the provider configuration.
        
        Args:
            config: LLM configuration specifying provider and settings
            
        Returns:
            Configured LLM client instance
            
        Raises:
            LLMConfigurationError: If provider is not supported
        """
        if config.provider not in cls._CLIENT_REGISTRY:
            raise LLMConfigurationError(
                f"Unsupported LLM provider: {config.provider.value}",
                config_key="provider",
                config_value=config.provider.value
            )
        
        client_class = cls._CLIENT_REGISTRY[config.provider]
        return client_class(config)
    
    @classmethod
    def register_client(cls, provider: LLMProvider, client_class: Type[LLMClient]) -> None:
        """
        Register a custom client class for a provider.
        
        Args:
            provider: LLM provider enum value
            client_class: Client class to register
        """
        cls._CLIENT_REGISTRY[provider] = client_class
    
    @classmethod
    def get_supported_providers(cls) -> list[LLMProvider]:
        """Get list of supported providers."""
        return list(cls._CLIENT_REGISTRY.keys())
    
    @classmethod
    def is_provider_supported(cls, provider: LLMProvider) -> bool:
        """Check if a provider is supported."""
        return provider in cls._CLIENT_REGISTRY


def create_llm_client(config: LLMConfiguration) -> LLMClient:
    """
    Convenience function to create an LLM client.
    
    Args:
        config: LLM configuration
        
    Returns:
        Configured LLM client instance
    """
    return LLMClientFactory.create_client(config)


def create_openai_client(
    api_key: str,
    model_name: str = "gpt-4",
    api_endpoint: str = "https://api.openai.com/v1",
    **kwargs
) -> OpenAIClient:
    """
    Convenience function to create an OpenAI client.
    
    Args:
        api_key: OpenAI API key
        model_name: Model name to use
        api_endpoint: API endpoint URL
        **kwargs: Additional configuration parameters
        
    Returns:
        Configured OpenAI client
    """
    config = LLMConfiguration(
        provider=LLMProvider.OPENAI,
        api_key=api_key,
        model_name=model_name,
        api_endpoint=api_endpoint,
        **kwargs
    )
    return OpenAIClient(config)


def create_anthropic_client(
    api_key: str,
    model_name: str = "claude-3-sonnet-20240229",
    api_endpoint: str = "https://api.anthropic.com",
    **kwargs
) -> AnthropicClient:
    """
    Convenience function to create an Anthropic client.
    
    Args:
        api_key: Anthropic API key
        model_name: Model name to use
        api_endpoint: API endpoint URL
        **kwargs: Additional configuration parameters
        
    Returns:
        Configured Anthropic client
    """
    config = LLMConfiguration(
        provider=LLMProvider.ANTHROPIC,
        api_key=api_key,
        model_name=model_name,
        api_endpoint=api_endpoint,
        **kwargs
    )
    return AnthropicClient(config)


def create_google_client(
    api_key: str,
    model_name: str = "gemini-1.5-pro",
    api_endpoint: str = "https://generativelanguage.googleapis.com",
    **kwargs
) -> GoogleClient:
    """
    Convenience function to create a Google AI client.
    
    Args:
        api_key: Google AI API key
        model_name: Model name to use (e.g., gemini-1.5-pro, gemini-1.5-flash)
        api_endpoint: API endpoint URL
        **kwargs: Additional configuration parameters
        
    Returns:
        Configured Google AI client
    """
    config = LLMConfiguration(
        provider=LLMProvider.GOOGLE,
        api_key=api_key,
        model_name=model_name,
        api_endpoint=api_endpoint,
        **kwargs
    )
    return GoogleClient(config)


def create_mock_client(
    model_name: str = "mock-model",
    **kwargs
) -> MockLLMClient:
    """
    Convenience function to create a mock client for testing.
    
    Args:
        model_name: Mock model name
        **kwargs: Additional configuration parameters
        
    Returns:
        Configured mock client
    """
    config = LLMConfiguration(
        provider=LLMProvider.MOCK,
        api_endpoint="http://localhost:8000",
        model_name=model_name,
        **kwargs
    )
    return MockLLMClient(config)