"""
LLM Client Abstraction

Provides a unified interface for different LLM providers with support for
function calling, streaming, and comprehensive error handling.
"""

import asyncio
import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, AsyncGenerator
import aiohttp
from datetime import datetime, timezone

from .models import (
    LLMConfiguration, LLMProvider, LLMRequest, LLMResponse, 
    Message, MessageRole, FunctionCall
)
from .exceptions import (
    LLMAPIError, LLMTimeoutError, LLMRateLimitError, 
    LLMConfigurationError, LLMResponseParsingError
)
from ..observability import get_tracer, get_metrics_collector, get_logger


class LLMClient(ABC):
    """Abstract base class for LLM clients with provider abstraction."""
    
    def __init__(self, config: LLMConfiguration):
        self.config = config
        self.logger = get_logger(f"polaris.llm.{self.__class__.__name__.lower()}")
        self.tracer = get_tracer()
        self.metrics = get_metrics_collector()
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Register LLM client metrics
        self._register_llm_client_metrics()
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self._ensure_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def _ensure_session(self) -> None:
        """Ensure HTTP session is created."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
    
    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    def _register_llm_client_metrics(self) -> None:
        """Register LLM client specific metrics."""
        try:
            # LLM API call metrics
            self.metrics.register_counter(
                "polaris_llm_client_requests_total",
                "Total LLM client requests made",
                ["provider", "model", "operation", "status"]
            )
            
            # LLM API latency
            self.metrics.register_histogram(
                "polaris_llm_client_request_duration_seconds",
                "Duration of LLM client requests",
                labels=["provider", "model", "operation"]
            )
            
            # Token usage metrics
            self.metrics.register_histogram(
                "polaris_llm_client_tokens_total",
                "Total tokens used in LLM requests",
                labels=["provider", "model", "token_type"]
            )
            
            # Function call metrics
            self.metrics.register_counter(
                "polaris_llm_client_function_calls_total",
                "Total function calls made by LLM",
                ["provider", "model", "function_name"]
            )
            
        except Exception as e:
            self.logger.warning("Failed to register LLM client metrics", extra={"error": str(e)})
    
    @abstractmethod
    async def generate_response(self, request: LLMRequest) -> LLMResponse:
        """Generate a response from the LLM."""
        pass
    
    @abstractmethod
    async def generate_stream(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """Generate a streaming response from the LLM."""
        pass
    
    @abstractmethod
    def supports_function_calling(self) -> bool:
        """Check if the client supports function calling."""
        pass
    
    @abstractmethod
    def get_provider(self) -> LLMProvider:
        """Get the provider type."""
        pass
    
    async def _make_request(
        self, 
        method: str, 
        url: str, 
        headers: Dict[str, str], 
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Make an HTTP request with retry logic."""
        await self._ensure_session()
        
        for attempt in range(self.config.max_retries + 1):
            try:
                async with self._session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=data
                ) as response:
                    response_data = await response.json()
                    
                    if response.status == 200:
                        return response_data
                    elif response.status == 429:
                        retry_after = int(response.headers.get('retry-after', 60))
                        raise LLMRateLimitError(
                            f"Rate limit exceeded",
                            retry_after=retry_after,
                            provider=self.get_provider().value
                        )
                    elif response.status >= 400:
                        error_msg = response_data.get('error', {}).get('message', 'Unknown error')
                        raise LLMAPIError(
                            f"API error: {error_msg}",
                            status_code=response.status,
                            api_endpoint=url,
                            provider=self.get_provider().value
                        )
                        
            except asyncio.TimeoutError:
                if attempt == self.config.max_retries:
                    raise LLMTimeoutError(
                        f"Request timed out after {self.config.timeout} seconds",
                        timeout_seconds=self.config.timeout,
                        provider=self.get_provider().value
                    )
                await asyncio.sleep(self.config.retry_delay * (2 ** attempt))
            except aiohttp.ClientError as e:
                if attempt == self.config.max_retries:
                    raise LLMAPIError(
                        f"Client error: {str(e)}",
                        provider=self.get_provider().value,
                        cause=e
                    )
                await asyncio.sleep(self.config.retry_delay * (2 ** attempt))
        
        raise LLMAPIError(
            f"Max retries ({self.config.max_retries}) exceeded",
            provider=self.get_provider().value
        )


class OpenAIClient(LLMClient):
    """OpenAI API client implementation."""
    
    def __init__(self, config: LLMConfiguration):
        if config.provider != LLMProvider.OPENAI:
            raise LLMConfigurationError(
                "OpenAIClient requires provider to be OPENAI",
                config_key="provider",
                config_value=config.provider.value
            )
        
        if not config.api_key:
            raise LLMConfigurationError(
                "OpenAI API key is required",
                config_key="api_key"
            )
        
        super().__init__(config)
    
    def get_provider(self) -> LLMProvider:
        """Get the provider type."""
        return LLMProvider.OPENAI
    
    def supports_function_calling(self) -> bool:
        """OpenAI supports function calling."""
        return True
    
    async def generate_response(self, request: LLMRequest) -> LLMResponse:
        """Generate response using OpenAI API."""
        correlation_id = str(uuid.uuid4())
        
        with self.tracer.trace_operation("llm_api_call") as span:
            span.add_tag("provider", "openai")
            span.add_tag("model", request.model_name)
            span.add_tag("operation", "generate_response")
            span.add_tag("correlation_id", correlation_id)
            span.add_tag("message_count", len(request.messages))
            span.add_tag("max_tokens", request.max_tokens)
            span.add_tag("temperature", request.temperature)
            span.add_tag("has_tools", bool(request.tools))
            
            start_time = time.time()
            
            try:
                headers = {
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                    "X-Correlation-ID": correlation_id
                }
                
                # Convert messages to OpenAI format
                messages = []
                for msg in request.messages:
                    openai_msg = {
                        "role": msg.role.value,
                        "content": msg.content
                    }
                    if msg.tool_calls:
                        openai_msg["tool_calls"] = [
                            {
                                "id": tc.call_id,
                                "type": "function",
                                "function": {
                                    "name": tc.tool_name,
                                    "arguments": json.dumps(tc.parameters)
                                }
                            }
                            for tc in msg.tool_calls
                        ]
                    if msg.tool_call_id:
                        openai_msg["tool_call_id"] = msg.tool_call_id
                    messages.append(openai_msg)
                
                data = {
                    "model": request.model_name,
                    "messages": messages,
                    "max_tokens": request.max_tokens,
                    "temperature": request.temperature
                }
                
                if request.tools and self.config.enable_function_calling:
                    data["tools"] = request.tools
                    span.add_tag("tool_count", len(request.tools))
                
                span.add_event("api_request_prepared")
                
                self.logger.info("Making LLM API request", extra={
                    "correlation_id": correlation_id,
                    "provider": "openai",
                    "model": request.model_name,
                    "message_count": len(messages),
                    "has_tools": bool(request.tools)
                })
                if request.tool_choice:
                    data["tool_choice"] = request.tool_choice
                
                # Make the API request
                response_data = await self._make_request(
                    method="POST",
                    url=f"{self.config.api_endpoint}/chat/completions",
                    headers=headers,
                    data=data
                )
                
                duration = time.time() - start_time
                span.add_event("api_response_received")
                span.add_tag("duration_seconds", duration)
                
                # Parse response
                response = self._parse_openai_response(response_data, request.request_id)
                
                # Update metrics
                self._update_api_metrics("openai", request.model_name, "generate_response", "success", duration, response)
                
                # Enhanced logging
                self.logger.info("LLM API request completed", extra={
                    "correlation_id": correlation_id,
                    "provider": "openai",
                    "model": request.model_name,
                    "duration_seconds": duration,
                    "response_tokens": response.usage.get("completion_tokens", 0) if response.usage else 0,
                    "total_tokens": response.usage.get("total_tokens", 0) if response.usage else 0,
                    "function_calls": len(response.function_calls),
                    "finish_reason": response.finish_reason
                })
                
                span.add_tag("success", True)
                span.add_tag("response_tokens", response.usage.get("completion_tokens", 0) if response.usage else 0)
                span.add_tag("function_calls_count", len(response.function_calls))
                
                return response
                
            except Exception as e:
                duration = time.time() - start_time
                span.set_error(e)
                span.add_tag("duration_seconds", duration)
                
                # Update failure metrics
                self._update_api_metrics("openai", request.model_name, "generate_response", "error", duration)
                
                self.logger.error("LLM API request failed", extra={
                    "correlation_id": correlation_id,
                    "provider": "openai",
                    "model": request.model_name,
                    "duration_seconds": duration,
                    "error": str(e)
                }, exc_info=e)
                
                if isinstance(e, (LLMAPIError, LLMTimeoutError, LLMRateLimitError)):
                    raise
                raise LLMAPIError(
                    f"Unexpected error: {str(e)}",
                    provider=self.get_provider().value,
                    cause=e
                )
    
    def _parse_openai_response(self, response_data: Dict[str, Any], request_id: str) -> LLMResponse:
        """Parse OpenAI API response."""
        try:
            choice = response_data["choices"][0]
            message = choice["message"]
            
            content = message.get("content", "")
            function_calls = []
            
            if "tool_calls" in message:
                for tool_call in message["tool_calls"]:
                    if tool_call["type"] == "function":
                        func = tool_call["function"]
                        function_calls.append(FunctionCall(
                            name=func["name"],
                            arguments=json.loads(func["arguments"]),
                            call_id=tool_call["id"]
                        ))
            
            return LLMResponse(
                content=content,
                model_name=response_data["model"],
                usage=response_data["usage"],
                function_calls=function_calls,
                finish_reason=choice["finish_reason"],
                request_id=request_id,
                metadata={"raw_response": response_data}
            )
            
        except (KeyError, json.JSONDecodeError) as e:
            raise LLMResponseParsingError(
                f"Failed to parse OpenAI response: {str(e)}",
                response_content=str(response_data),
                expected_format="OpenAI chat completion format",
                provider=self.get_provider().value,
                cause=e
            )
    
    async def generate_stream(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """Generate streaming response (basic implementation)."""
        # For now, return non-streaming response as single chunk
        response = await self.generate_response(request)
        yield response.content
    
    def _update_api_metrics(
        self, 
        provider: str, 
        model: str, 
        operation: str, 
        status: str, 
        duration: float, 
        response: Optional[LLMResponse] = None
    ) -> None:
        """Update LLM API metrics."""
        try:
            # Request counter
            requests_counter = self.metrics.get_metric("polaris_llm_client_requests_total")
            if requests_counter:
                requests_counter.increment(labels={
                    "provider": provider,
                    "model": model,
                    "operation": operation,
                    "status": status
                })
            
            # Duration histogram
            duration_histogram = self.metrics.get_metric("polaris_llm_client_request_duration_seconds")
            if duration_histogram:
                duration_histogram.observe(duration, labels={
                    "provider": provider,
                    "model": model,
                    "operation": operation
                })
            
            # Token usage metrics
            if response and response.usage:
                tokens_histogram = self.metrics.get_metric("polaris_llm_client_tokens_total")
                if tokens_histogram:
                    # Prompt tokens
                    if "prompt_tokens" in response.usage:
                        tokens_histogram.observe(response.usage["prompt_tokens"], labels={
                            "provider": provider,
                            "model": model,
                            "token_type": "prompt"
                        })
                    
                    # Completion tokens
                    if "completion_tokens" in response.usage:
                        tokens_histogram.observe(response.usage["completion_tokens"], labels={
                            "provider": provider,
                            "model": model,
                            "token_type": "completion"
                        })
            
            # Function call metrics
            if response and response.function_calls:
                function_calls_counter = self.metrics.get_metric("polaris_llm_client_function_calls_total")
                if function_calls_counter:
                    for func_call in response.function_calls:
                        function_calls_counter.increment(labels={
                            "provider": provider,
                            "model": model,
                            "function_name": func_call.name
                        })
                        
        except Exception as e:
            self.logger.debug(f"Failed to update API metrics: {e}")


class AnthropicClient(LLMClient):
    """Anthropic API client implementation."""
    
    def __init__(self, config: LLMConfiguration):
        if config.provider != LLMProvider.ANTHROPIC:
            raise LLMConfigurationError(
                "AnthropicClient requires provider to be ANTHROPIC",
                config_key="provider",
                config_value=config.provider.value
            )
        
        if not config.api_key:
            raise LLMConfigurationError(
                "Anthropic API key is required",
                config_key="api_key"
            )
        
        super().__init__(config)
    
    def get_provider(self) -> LLMProvider:
        """Get the provider type."""
        return LLMProvider.ANTHROPIC
    
    def supports_function_calling(self) -> bool:
        """Anthropic supports tool calling."""
        return True
    
    async def generate_response(self, request: LLMRequest) -> LLMResponse:
        """Generate response using Anthropic API."""
        headers = {
            "x-api-key": self.config.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        
        # Convert messages to Anthropic format
        messages = []
        system_message = None
        
        for msg in request.messages:
            if msg.role == MessageRole.SYSTEM:
                system_message = msg.content
            else:
                messages.append({
                    "role": msg.role.value,
                    "content": msg.content
                })
        
        data = {
            "model": request.model_name,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature
        }
        
        if system_message:
            data["system"] = system_message
        
        if request.tools and self.config.enable_function_calling:
            data["tools"] = request.tools
        
        try:
            response_data = await self._make_request(
                method="POST",
                url=f"{self.config.api_endpoint}/messages",
                headers=headers,
                data=data
            )
            
            return self._parse_anthropic_response(response_data, request.request_id)
            
        except Exception as e:
            if isinstance(e, (LLMAPIError, LLMTimeoutError, LLMRateLimitError)):
                raise
            raise LLMAPIError(
                f"Unexpected error: {str(e)}",
                provider=self.get_provider().value,
                cause=e
            )
    
    def _parse_anthropic_response(self, response_data: Dict[str, Any], request_id: str) -> LLMResponse:
        """Parse Anthropic API response."""
        try:
            content_blocks = response_data["content"]
            content = ""
            function_calls = []
            
            for block in content_blocks:
                if block["type"] == "text":
                    content += block["text"]
                elif block["type"] == "tool_use":
                    function_calls.append(FunctionCall(
                        name=block["name"],
                        arguments=block["input"],
                        call_id=block["id"]
                    ))
            
            return LLMResponse(
                content=content,
                model_name=response_data["model"],
                usage=response_data["usage"],
                function_calls=function_calls,
                finish_reason=response_data["stop_reason"],
                request_id=request_id,
                metadata={"raw_response": response_data}
            )
            
        except KeyError as e:
            raise LLMResponseParsingError(
                f"Failed to parse Anthropic response: {str(e)}",
                response_content=str(response_data),
                expected_format="Anthropic messages format",
                provider=self.get_provider().value,
                cause=e
            )
    
    async def generate_stream(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """Generate streaming response (basic implementation)."""
        # For now, return non-streaming response as single chunk
        response = await self.generate_response(request)
        yield response.content


class GoogleClient(LLMClient):
    """Google AI API client implementation (Gemini models)."""
    
    def __init__(self, config: LLMConfiguration):
        if config.provider != LLMProvider.GOOGLE:
            raise LLMConfigurationError(
                "GoogleClient requires provider to be GOOGLE",
                config_key="provider",
                config_value=config.provider.value
            )
        
        if not config.api_key:
            raise LLMConfigurationError(
                "Google API key is required",
                config_key="api_key"
            )
        
        super().__init__(config)
    
    def get_provider(self) -> LLMProvider:
        """Get the provider type."""
        return LLMProvider.GOOGLE
    
    def supports_function_calling(self) -> bool:
        """Google Gemini supports function calling."""
        return True
    
    async def generate_response(self, request: LLMRequest) -> LLMResponse:
        """Generate response using Google AI API."""
        headers = {
            "Content-Type": "application/json"
        }
        
        # Convert messages to Google format
        contents = []
        system_instruction = None
        
        for msg in request.messages:
            if msg.role == MessageRole.SYSTEM:
                system_instruction = {"parts": [{"text": msg.content}]}
            elif msg.role == MessageRole.USER:
                contents.append({
                    "role": "user",
                    "parts": [{"text": msg.content}]
                })
            elif msg.role == MessageRole.ASSISTANT:
                parts = []
                if msg.content:
                    parts.append({"text": msg.content})
                
                # Handle function calls
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        parts.append({
                            "functionCall": {
                                "name": tc.tool_name,
                                "args": tc.parameters
                            }
                        })
                
                contents.append({
                    "role": "model",
                    "parts": parts
                })
            elif msg.role == MessageRole.TOOL:
                # Tool response
                contents.append({
                    "role": "function",
                    "parts": [{
                        "functionResponse": {
                            "name": msg.tool_call_id or "unknown_function",
                            "response": {"result": msg.content}
                        }
                    }]
                })
        
        # Build request data
        data = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": request.max_tokens,
                "temperature": request.temperature
            }
        }
        
        if system_instruction:
            data["systemInstruction"] = system_instruction
        
        # Add function declarations if tools are provided
        if request.tools and self.config.enable_function_calling:
            function_declarations = []
            for tool in request.tools:
                if tool.get("type") == "function":
                    func = tool["function"]
                    function_declarations.append({
                        "name": func["name"],
                        "description": func["description"],
                        "parameters": func["parameters"]
                    })
            
            if function_declarations:
                data["tools"] = [{"functionDeclarations": function_declarations}]
        
        # Construct URL with API key
        url = f"{self.config.api_endpoint}/v1beta/models/{request.model_name}:generateContent"
        if "?" in url:
            url += f"&key={self.config.api_key}"
        else:
            url += f"?key={self.config.api_key}"
        
        try:
            response_data = await self._make_request(
                method="POST",
                url=url,
                headers=headers,
                data=data
            )
            
            return self._parse_google_response(response_data, request.request_id)
            
        except Exception as e:
            if isinstance(e, (LLMAPIError, LLMTimeoutError, LLMRateLimitError)):
                raise
            raise LLMAPIError(
                f"Unexpected error: {str(e)}",
                provider=self.get_provider().value,
                cause=e
            )
    
    def _parse_google_response(self, response_data: Dict[str, Any], request_id: str) -> LLMResponse:
        """Parse Google AI API response."""
        try:
            candidates = response_data.get("candidates", [])
            if not candidates:
                raise LLMResponseParsingError(
                    "No candidates in Google response",
                    response_content=str(response_data),
                    expected_format="Google AI response format",
                    provider=self.get_provider().value
                )
            
            candidate = candidates[0]
            content_parts = candidate.get("content", {}).get("parts", [])
            
            content = ""
            function_calls = []
            
            for part in content_parts:
                if "text" in part:
                    content += part["text"]
                elif "functionCall" in part:
                    func_call = part["functionCall"]
                    function_calls.append(FunctionCall(
                        name=func_call["name"],
                        arguments=func_call.get("args", {}),
                        call_id=f"google_{func_call['name']}_{len(function_calls)}"
                    ))
            
            # Extract usage information if available
            usage_metadata = response_data.get("usageMetadata", {})
            usage = {
                "prompt_tokens": usage_metadata.get("promptTokenCount", 0),
                "completion_tokens": usage_metadata.get("candidatesTokenCount", 0),
                "total_tokens": usage_metadata.get("totalTokenCount", 0)
            }
            
            finish_reason = candidate.get("finishReason", "STOP").lower()
            if finish_reason == "stop":
                finish_reason = "stop"
            elif finish_reason == "max_tokens":
                finish_reason = "length"
            else:
                finish_reason = "other"
            
            return LLMResponse(
                content=content,
                model_name=response_data.get("modelVersion", "unknown"),
                usage=usage,
                function_calls=function_calls,
                finish_reason=finish_reason,
                request_id=request_id,
                metadata={"raw_response": response_data}
            )
            
        except KeyError as e:
            raise LLMResponseParsingError(
                f"Failed to parse Google response: {str(e)}",
                response_content=str(response_data),
                expected_format="Google AI response format",
                provider=self.get_provider().value,
                cause=e
            )
    
    async def generate_stream(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """Generate streaming response using Google AI API."""
        # For now, return non-streaming response as single chunk
        # TODO: Implement actual streaming using Google's streaming API
        response = await self.generate_response(request)
        yield response.content


class MockLLMClient(LLMClient):
    """Mock LLM client for testing and development."""
    
    def __init__(self, config: Optional[LLMConfiguration] = None):
        if config is None:
            config = LLMConfiguration(
                provider=LLMProvider.MOCK,
                api_endpoint="http://localhost:8000",
                model_name="mock-model"
            )
        super().__init__(config)
        self.mock_responses: List[str] = [
            "This is a mock response from the LLM.",
            "Another mock response for testing purposes.",
            "Mock LLM is working correctly."
        ]
        self.response_index = 0
    
    def get_provider(self) -> LLMProvider:
        """Get the provider type."""
        return LLMProvider.MOCK
    
    def supports_function_calling(self) -> bool:
        """Mock client supports function calling."""
        return True
    
    async def generate_response(self, request: LLMRequest) -> LLMResponse:
        """Generate mock response."""
        # Simulate API delay
        await asyncio.sleep(0.1)
        
        content = self.mock_responses[self.response_index % len(self.mock_responses)]
        self.response_index += 1
        
        # Mock function calls if tools are provided
        function_calls = []
        if request.tools and len(request.tools) > 0:
            tool = request.tools[0]
            if tool.get("type") == "function":
                func_name = tool["function"]["name"]
                function_calls.append(FunctionCall(
                    name=func_name,
                    arguments={"mock": "parameters"}
                ))
        
        return LLMResponse(
            content=content,
            model_name=request.model_name,
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            function_calls=function_calls,
            finish_reason="stop",
            request_id=request.request_id,
            metadata={"mock": True}
        )
    
    async def generate_stream(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """Generate mock streaming response."""
        content = self.mock_responses[self.response_index % len(self.mock_responses)]
        self.response_index += 1
        
        # Simulate streaming by yielding words
        words = content.split()
        for word in words:
            await asyncio.sleep(0.05)  # Simulate streaming delay
            yield word + " "
    
    def set_mock_responses(self, responses: List[str]) -> None:
        """Set custom mock responses."""
        self.mock_responses = responses
        self.response_index = 0