"""
Agentic LLM Execution Engine

Provides the core execution engine for agentic LLM interactions including
function calling interface, tool execution validation, reasoning trace logging,
and adaptive context management.
"""

import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass, field

from ..infrastructure.llm.client import LLMClient
from ..infrastructure.llm.models import (
    LLMRequest, LLMResponse, Message, MessageRole, AgenticConversation, 
    ToolCall, FunctionCall
)
from ..infrastructure.llm.tool_registry import ToolRegistry, ToolResult
from ..infrastructure.llm.exceptions import LLMAPIError, LLMToolError
from ..infrastructure.observability.factory import get_control_logger


@dataclass
class ExecutionContext:
    """Context for agentic execution sessions."""
    session_id: str
    system_id: str
    objective: str
    max_iterations: int = 10
    max_context_tokens: int = 8000
    tool_timeout_seconds: float = 30.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReasoningTrace:
    """Detailed trace of reasoning steps and decisions."""
    trace_id: str
    session_id: str
    steps: List[Dict[str, Any]] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    decisions: List[Dict[str, Any]] = field(default_factory=list)
    context_management: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def add_step(self, step_type: str, description: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Add a reasoning step to the trace."""
        self.steps.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "step_type": step_type,
            "description": description,
            "metadata": metadata or {}
        })
    
    def add_tool_call(self, tool_name: str, parameters: Dict[str, Any], result: ToolResult) -> None:
        """Add a tool call to the trace."""
        self.tool_calls.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool_name": tool_name,
            "parameters": parameters,
            "success": result.success,
            "execution_time": result.execution_time,
            "error_message": result.error_message
        })
    
    def add_decision(self, decision_type: str, rationale: str, outcome: Any) -> None:
        """Add a decision point to the trace."""
        self.decisions.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "decision_type": decision_type,
            "rationale": rationale,
            "outcome": outcome
        })
    
    def add_context_event(self, event_type: str, description: str, tokens_used: Optional[int] = None) -> None:
        """Add a context management event to the trace."""
        self.context_management.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "description": description,
            "tokens_used": tokens_used
        })


class AgenticExecutionEngine:
    """
    Core execution engine for agentic LLM interactions.
    
    Provides comprehensive execution capabilities including:
    - Function calling interface for LLM tool invocation
    - Tool execution validation and error handling
    - Reasoning trace logging for transparency and debugging
    - Adaptive context management based on reasoning complexity
    - Session management for multi-turn conversations
    """
    
    def __init__(
        self,
        llm_client: LLMClient,
        tool_registry: ToolRegistry,
        enable_tracing: bool = True,
        enable_context_management: bool = True
    ):
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.enable_tracing = enable_tracing
        self.enable_context_management = enable_context_management
        
        # Active sessions and traces
        self.active_sessions: Dict[str, AgenticConversation] = {}
        self.reasoning_traces: Dict[str, ReasoningTrace] = {}
        
        # Context management settings
        self.context_compression_threshold = 0.8  # Compress when 80% of max tokens used
        self.context_summary_ratio = 0.3  # Keep 30% of context when compressing
        
        # Setup logging
        self.logger = get_control_logger("agentic_execution_engine")
    
    async def start_session(
        self,
        context: ExecutionContext,
        initial_prompt: str,
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Start a new agentic execution session.
        
        Args:
            context: Execution context with session parameters
            initial_prompt: Initial user prompt to start the conversation
            system_prompt: Optional system prompt to set agent behavior
            
        Returns:
            Session ID for tracking the conversation
        """
        # Create new conversation
        conversation = AgenticConversation(
            conversation_id=context.session_id,
            max_iterations=context.max_iterations,
            context={
                "system_id": context.system_id,
                "objective": context.objective,
                "max_context_tokens": context.max_context_tokens,
                "tool_timeout": context.tool_timeout_seconds
            }
        )
        
        # Add system prompt if provided
        if system_prompt:
            conversation.add_message(Message(
                role=MessageRole.SYSTEM,
                content=system_prompt
            ))
        
        # Add initial user message
        conversation.add_message(Message(
            role=MessageRole.USER,
            content=initial_prompt,
            metadata={"session_start": True}
        ))
        
        # Store session
        self.active_sessions[context.session_id] = conversation
        
        # Initialize reasoning trace if enabled
        if self.enable_tracing:
            trace = ReasoningTrace(
                trace_id=f"{context.session_id}_trace",
                session_id=context.session_id
            )
            trace.add_step("session_start", f"Started session with objective: {context.objective}")
            self.reasoning_traces[context.session_id] = trace
        
        self.logger.info(f"Started agentic session {context.session_id} for system {context.system_id}")
        
        return context.session_id
    
    async def execute_iteration(self, session_id: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Execute one iteration of the agentic conversation.
        
        Args:
            session_id: ID of the active session
            
        Returns:
            Tuple of (is_complete, iteration_result)
        """
        conversation = self.active_sessions.get(session_id)
        if not conversation:
            raise ValueError(f"No active session found: {session_id}")
        
        trace = self.reasoning_traces.get(session_id) if self.enable_tracing else None
        
        try:
            # Check if conversation is already complete
            if conversation.is_complete:
                return True, {"status": "already_complete", "result": conversation.final_result}
            
            # Check iteration limit
            if conversation.current_iteration >= conversation.max_iterations:
                conversation.complete({"status": "max_iterations_reached"})
                if trace:
                    trace.add_decision("iteration_limit", "Reached maximum iterations", "session_complete")
                return True, {"status": "max_iterations", "iterations": conversation.current_iteration}
            
            # Manage context if enabled
            if self.enable_context_management:
                await self._manage_context(conversation, trace)
            
            # Prepare LLM request
            request = await self._prepare_llm_request(conversation, trace)
            
            # Execute LLM call
            if trace:
                trace.add_step("llm_call", f"Making LLM request with {len(request.messages)} messages")
            
            response = await self.llm_client.generate_response(request)
            
            # Process response
            result = await self._process_llm_response(response, conversation, trace)
            
            # Increment iteration
            conversation.increment_iteration()
            
            # Check if conversation is complete
            if conversation.is_complete:
                if trace:
                    trace.add_step("session_complete", "Conversation marked as complete")
                return True, {"status": "complete", "result": conversation.final_result}
            
            return False, result
            
        except Exception as e:
            self.logger.error(f"Error in session {session_id} iteration {conversation.current_iteration}: {str(e)}")
            
            if trace:
                trace.add_step("error", f"Iteration failed: {str(e)}", {"error_type": type(e).__name__})
            
            # Mark conversation as complete with error
            conversation.complete({
                "status": "error",
                "error": str(e),
                "iteration": conversation.current_iteration
            })
            
            return True, {"status": "error", "error": str(e)}
    
    async def _prepare_llm_request(
        self, 
        conversation: AgenticConversation, 
        trace: Optional[ReasoningTrace]
    ) -> LLMRequest:
        """Prepare LLM request with tools and context."""
        
        # Get available tools
        tools = None
        if self.tool_registry.list_tools():
            tools = self.tool_registry.get_tool_schemas("openai")
            if trace:
                trace.add_step("tools_prepared", f"Prepared {len(tools)} tools for LLM")
        
        # Create request
        request = LLMRequest(
            messages=conversation.messages,
            model_name=self.llm_client.config.model_name,
            max_tokens=self.llm_client.config.max_tokens,
            temperature=self.llm_client.config.temperature,
            tools=tools,
            tool_choice="auto" if tools else None
        )
        
        return request
    
    async def _process_llm_response(
        self,
        response: LLMResponse,
        conversation: AgenticConversation,
        trace: Optional[ReasoningTrace]
    ) -> Dict[str, Any]:
        """Process LLM response including function calls."""
        
        # Add assistant message to conversation
        assistant_message = Message(
            role=MessageRole.ASSISTANT,
            content=response.content,
            metadata={
                "response_id": response.response_id,
                "finish_reason": response.finish_reason,
                "usage": response.usage
            }
        )
        conversation.add_message(assistant_message)
        
        result = {
            "response_content": response.content,
            "function_calls": len(response.function_calls),
            "finish_reason": response.finish_reason
        }
        
        # Process function calls if present
        if response.function_calls:
            if trace:
                trace.add_step("function_calls", f"Processing {len(response.function_calls)} function calls")
            
            tool_results = await self._execute_function_calls(response.function_calls, conversation, trace)
            result["tool_results"] = tool_results
            
            # Check if we should continue or complete
            if self._should_complete_conversation(response, tool_results):
                conversation.complete({
                    "status": "natural_completion",
                    "final_response": response.content,
                    "tool_calls_executed": len(tool_results)
                })
                if trace:
                    trace.add_decision("completion", "Natural completion after tool execution", "complete")
        else:
            # No function calls, likely a final response
            if self._is_final_response(response):
                conversation.complete({
                    "status": "final_response",
                    "content": response.content
                })
                if trace:
                    trace.add_decision("completion", "Final response without tool calls", "complete")
        
        return result
    
    async def _execute_function_calls(
        self,
        function_calls: List[FunctionCall],
        conversation: AgenticConversation,
        trace: Optional[ReasoningTrace]
    ) -> List[Dict[str, Any]]:
        """Execute function calls and add results to conversation."""
        
        tool_results = []
        
        for func_call in function_calls:
            try:
                # Validate tool exists
                tool = self.tool_registry.get_tool(func_call.name)
                if not tool:
                    error_msg = f"Tool not found: {func_call.name}"
                    self.logger.warning(error_msg)
                    
                    # Add error message to conversation
                    error_message = Message(
                        role=MessageRole.TOOL,
                        content=json.dumps({"error": error_msg}),
                        tool_call_id=func_call.call_id,
                        metadata={"error": True, "tool_name": func_call.name}
                    )
                    conversation.add_message(error_message)
                    
                    tool_results.append({
                        "tool_name": func_call.name,
                        "success": False,
                        "error": error_msg
                    })
                    continue
                
                # Execute tool with timeout and validation
                if trace:
                    trace.add_step("tool_execution", f"Executing tool {func_call.name}")
                
                tool_result = await self._execute_tool_with_validation(
                    func_call, conversation, trace
                )
                
                # Add tool result to conversation
                result_content = json.dumps(tool_result.result) if tool_result.success else f"Tool error: {tool_result.error_message}"
                
                tool_message = Message(
                    role=MessageRole.TOOL,
                    content=result_content,
                    tool_call_id=func_call.call_id,
                    metadata={
                        "tool_name": func_call.name,
                        "success": tool_result.success,
                        "execution_time": tool_result.execution_time
                    }
                )
                conversation.add_message(tool_message)
                
                # Add to conversation tool calls
                tool_call = ToolCall(
                    tool_name=func_call.name,
                    parameters=func_call.arguments,
                    call_id=func_call.call_id
                )
                conversation.add_tool_call(tool_call)
                
                # Add to trace
                if trace:
                    trace.add_tool_call(func_call.name, func_call.arguments, tool_result)
                
                tool_results.append({
                    "tool_name": func_call.name,
                    "success": tool_result.success,
                    "execution_time": tool_result.execution_time,
                    "result_size": len(str(tool_result.result))
                })
                
            except Exception as e:
                self.logger.error(f"Error executing tool {func_call.name}: {str(e)}")
                
                # Add error to conversation
                error_message = Message(
                    role=MessageRole.TOOL,
                    content=json.dumps({"error": f"Tool execution failed: {str(e)}"}),
                    tool_call_id=func_call.call_id,
                    metadata={"error": True, "tool_name": func_call.name}
                )
                conversation.add_message(error_message)
                
                if trace:
                    trace.add_step("tool_error", f"Tool {func_call.name} failed: {str(e)}")
                
                tool_results.append({
                    "tool_name": func_call.name,
                    "success": False,
                    "error": str(e)
                })
        
        return tool_results
    
    async def _execute_tool_with_validation(
        self,
        func_call: FunctionCall,
        conversation: AgenticConversation,
        trace: Optional[ReasoningTrace]
    ) -> ToolResult:
        """Execute tool with parameter validation and timeout handling."""
        
        # Get timeout from conversation context
        timeout = conversation.context.get("tool_timeout", 30.0)
        
        try:
            # Execute tool with timeout
            import asyncio
            tool_result = await asyncio.wait_for(
                self.tool_registry.execute_tool(
                    func_call.name,
                    func_call.arguments,
                    func_call.call_id
                ),
                timeout=timeout
            )
            
            return tool_result
            
        except asyncio.TimeoutError:
            error_msg = f"Tool {func_call.name} timed out after {timeout} seconds"
            self.logger.warning(error_msg)
            
            return ToolResult(
                call_id=func_call.call_id,
                tool_name=func_call.name,
                success=False,
                result={},
                error_message=error_msg,
                execution_time=timeout
            )
        
        except Exception as e:
            return ToolResult(
                call_id=func_call.call_id,
                tool_name=func_call.name,
                success=False,
                result={},
                error_message=str(e),
                execution_time=0.0
            )
    
    async def _manage_context(
        self, 
        conversation: AgenticConversation, 
        trace: Optional[ReasoningTrace]
    ) -> None:
        """Manage conversation context to stay within token limits."""
        
        max_tokens = conversation.context.get("max_context_tokens", 8000)
        
        # Estimate current token usage (rough approximation)
        current_tokens = self._estimate_token_usage(conversation.messages)
        
        if trace:
            trace.add_context_event("token_check", f"Estimated {current_tokens} tokens", current_tokens)
        
        # Check if we need to compress context
        if current_tokens > max_tokens * self.context_compression_threshold:
            if trace:
                trace.add_context_event("compression_triggered", "Context compression needed")
            
            await self._compress_context(conversation, max_tokens, trace)
    
    def _estimate_token_usage(self, messages: List[Message]) -> int:
        """Rough estimation of token usage for messages."""
        total_chars = sum(len(msg.content) for msg in messages)
        # Rough approximation: 1 token ≈ 4 characters
        return total_chars // 4
    
    async def _compress_context(
        self, 
        conversation: AgenticConversation, 
        max_tokens: int, 
        trace: Optional[ReasoningTrace]
    ) -> None:
        """Compress conversation context by summarizing older messages."""
        
        target_tokens = int(max_tokens * self.context_summary_ratio)
        
        # Keep system message and recent messages, summarize the middle
        if len(conversation.messages) <= 3:
            return  # Too few messages to compress
        
        # Find split points
        system_messages = [msg for msg in conversation.messages if msg.role == MessageRole.SYSTEM]
        other_messages = [msg for msg in conversation.messages if msg.role != MessageRole.SYSTEM]
        
        if len(other_messages) <= 2:
            return  # Not enough to compress
        
        # Keep first and last few messages, summarize middle
        keep_recent = 3
        keep_early = 1
        
        if len(other_messages) <= keep_recent + keep_early:
            return
        
        early_messages = other_messages[:keep_early]
        middle_messages = other_messages[keep_early:-keep_recent]
        recent_messages = other_messages[-keep_recent:]
        
        # Create summary of middle messages
        summary_content = self._create_message_summary(middle_messages)
        
        summary_message = Message(
            role=MessageRole.USER,
            content=f"[CONTEXT SUMMARY] Previous conversation summary: {summary_content}",
            metadata={"compressed": True, "original_messages": len(middle_messages)}
        )
        
        # Rebuild message list
        new_messages = system_messages + early_messages + [summary_message] + recent_messages
        conversation.messages = new_messages
        
        if trace:
            trace.add_context_event(
                "compression_complete", 
                f"Compressed {len(middle_messages)} messages into summary",
                self._estimate_token_usage(new_messages)
            )
    
    def _create_message_summary(self, messages: List[Message]) -> str:
        """Create a summary of messages for context compression."""
        
        summaries = []
        
        for msg in messages:
            if msg.role == MessageRole.USER:
                summaries.append(f"User asked: {msg.content[:100]}...")
            elif msg.role == MessageRole.ASSISTANT:
                summaries.append(f"Assistant responded: {msg.content[:100]}...")
            elif msg.role == MessageRole.TOOL:
                tool_name = msg.metadata.get("tool_name", "unknown")
                summaries.append(f"Tool {tool_name} executed")
        
        return " | ".join(summaries)
    
    def _should_complete_conversation(
        self, 
        response: LLMResponse, 
        tool_results: List[Dict[str, Any]]
    ) -> bool:
        """Determine if conversation should be completed based on response and tool results."""
        
        # Complete if finish reason indicates completion
        if response.finish_reason in ["stop", "length"]:
            return True
        
        # Complete if response contains completion indicators
        completion_indicators = [
            "recommendation", "conclusion", "final analysis", 
            "in summary", "to conclude", "my recommendation"
        ]
        
        content_lower = response.content.lower()
        if any(indicator in content_lower for indicator in completion_indicators):
            return True
        
        # Complete if no more tool calls and response is substantial
        if not response.function_calls and len(response.content) > 100:
            return True
        
        return False
    
    def _is_final_response(self, response: LLMResponse) -> bool:
        """Check if response appears to be a final response."""
        
        # No function calls and substantial content
        if not response.function_calls and len(response.content) > 50:
            return True
        
        # Finish reason indicates completion
        if response.finish_reason == "stop":
            return True
        
        return False
    
    def get_session_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get status of an active session."""
        
        conversation = self.active_sessions.get(session_id)
        if not conversation:
            return None
        
        trace = self.reasoning_traces.get(session_id)
        
        return {
            "session_id": session_id,
            "is_complete": conversation.is_complete,
            "current_iteration": conversation.current_iteration,
            "max_iterations": conversation.max_iterations,
            "message_count": len(conversation.messages),
            "tool_calls_made": len(conversation.tool_calls),
            "reasoning_steps": len(trace.steps) if trace else 0,
            "created_at": conversation.created_at.isoformat(),
            "updated_at": conversation.updated_at.isoformat()
        }
    
    def get_reasoning_trace(self, session_id: str) -> Optional[ReasoningTrace]:
        """Get the reasoning trace for a session."""
        return self.reasoning_traces.get(session_id)
    
    def cleanup_session(self, session_id: str) -> bool:
        """Clean up a completed session."""
        
        conversation = self.active_sessions.pop(session_id, None)
        trace = self.reasoning_traces.pop(session_id, None)
        
        if conversation:
            self.logger.info(f"Cleaned up session {session_id}")
            return True
        
        return False
    
    def list_active_sessions(self) -> List[str]:
        """List all active session IDs."""
        return list(self.active_sessions.keys())