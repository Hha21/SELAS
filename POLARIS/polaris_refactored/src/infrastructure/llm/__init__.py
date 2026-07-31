"""
LLM Integration Infrastructure

Provides comprehensive LLM integration capabilities including client abstraction,
prompt management, response parsing, tool registry, conversation management,
and caching for the POLARIS adaptation framework.
"""

from .client import LLMClient, OpenAIClient, AnthropicClient, GoogleClient, MockLLMClient
from .client_factory import (
    LLMClientFactory, create_llm_client, create_openai_client, 
    create_anthropic_client, create_google_client, create_mock_client
)
from .prompt_manager import PromptManager, PromptTemplate, ConversationFlow
from .response_parser import ResponseParser, JSONSchemaValidator, FunctionCallParser
from .tool_registry import ToolRegistry, BaseTool, ToolSchema, ToolResult
from .conversation_manager import ConversationManager, Conversation, Message
from .cache import LLMCache, LLMCacheEntry
from .models import (
    LLMConfiguration,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    FunctionCall,
    ToolCall,
    MessageRole,
    AgenticConversation
)
from .exceptions import (
    LLMIntegrationError,
    LLMAPIError,
    LLMResponseParsingError,
    LLMToolError,
    LLMConfigurationError
)

__all__ = [
    # Core client classes
    'LLMClient',
    'OpenAIClient', 
    'AnthropicClient',
    'GoogleClient',
    'MockLLMClient',
    
    # Factory functions
    'LLMClientFactory',
    'create_llm_client',
    'create_openai_client',
    'create_anthropic_client',
    'create_google_client',
    'create_mock_client',
    
    # Prompt management
    'PromptManager',
    'PromptTemplate',
    'ConversationFlow',
    
    # Response parsing
    'ResponseParser',
    'JSONSchemaValidator',
    'FunctionCallParser',
    
    # Tool system
    'ToolRegistry',
    'BaseTool',
    'ToolSchema',
    'ToolResult',
    
    # Conversation management
    'ConversationManager',
    'Conversation',
    'MessageRole',
    'Message',
    
    # Caching
    'LLMCache',
    'LLMCacheEntry',
    
    # Models
    'LLMConfiguration',
    'LLMProvider',
    'LLMRequest',
    'LLMResponse',
    'FunctionCall',
    'ToolCall',
    'AgenticConversation',
    
    # Exceptions
    'LLMIntegrationError',
    'LLMAPIError',
    'LLMResponseParsingError',
    'LLMToolError',
    'LLMConfigurationError'
]