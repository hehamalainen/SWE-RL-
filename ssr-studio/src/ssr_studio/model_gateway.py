"""
Model Gateway for SSR Studio.

Provides a unified interface to different LLM providers:
- OpenAI (GPT-4, etc.)
- Anthropic (Claude)
- Local models via vLLM

Handles tool calling, rate limiting, and token counting.
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Callable

import httpx
import tiktoken
import structlog

from ssr_studio.config import settings

logger = structlog.get_logger()


class Role(str, Enum):
    """Message roles."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    """A chat message."""
    role: Role
    content: str
    name: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None


@dataclass
class ToolDefinition:
    """Definition of a tool the model can call."""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema


@dataclass
class ToolCall:
    """A tool call from the model."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class GenerationResult:
    """Result of a model generation."""
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ModelProvider(ABC):
    """Abstract base class for model providers."""
    
    @abstractmethod
    async def generate(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stop: list[str] | None = None,
    ) -> GenerationResult:
        """Generate a response from the model."""
        pass
    
    @abstractmethod
    async def generate_stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stop: list[str] | None = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming response."""
        pass
    
    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        pass


class OpenAIProvider(ModelProvider):
    """OpenAI API provider."""
    
    def __init__(self, api_key: str | None = None, model: str | None = None):
        import openai
        
        self.api_key = api_key or (
            settings.openai_api_key.get_secret_value()
            if settings.openai_api_key else None
        )
        self.model = model or settings.openai_model
        self.client = openai.AsyncOpenAI(api_key=self.api_key)
        
        # Token counter
        try:
            self._encoding = tiktoken.encoding_for_model(self.model)
        except KeyError:
            self._encoding = tiktoken.get_encoding("cl100k_base")
    
    def _convert_messages(self, messages: list[Message]) -> list[dict]:
        """Convert messages to OpenAI format."""
        result = []
        for msg in messages:
            d = {"role": msg.role.value, "content": msg.content}
            if msg.name:
                d["name"] = msg.name
            if msg.tool_calls:
                d["tool_calls"] = msg.tool_calls
            if msg.tool_call_id:
                d["tool_call_id"] = msg.tool_call_id
            result.append(d)
        return result
    
    def _convert_tools(self, tools: list[ToolDefinition]) -> list[dict]:
        """Convert tools to OpenAI format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]
    
    async def generate(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stop: list[str] | None = None,
    ) -> GenerationResult:
        """Generate a response using OpenAI API."""
        kwargs = {
            "model": self.model,
            "messages": self._convert_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        if tools:
            kwargs["tools"] = self._convert_tools(tools)
        if stop:
            kwargs["stop"] = stop
        
        response = await self.client.chat.completions.create(**kwargs)
        
        choice = response.choices[0]
        message = choice.message
        
        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments),
                ))
        
        return GenerationResult(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
            completion_tokens=response.usage.completion_tokens if response.usage else 0,
            total_tokens=response.usage.total_tokens if response.usage else 0,
        )
    
    async def generate_stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stop: list[str] | None = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming response using OpenAI API."""
        kwargs = {
            "model": self.model,
            "messages": self._convert_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        
        if tools:
            kwargs["tools"] = self._convert_tools(tools)
        if stop:
            kwargs["stop"] = stop
        
        stream = await self.client.chat.completions.create(**kwargs)
        
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    
    def count_tokens(self, text: str) -> int:
        """Count tokens using tiktoken."""
        return len(self._encoding.encode(text))


class AnthropicProvider(ModelProvider):
    """Anthropic API provider."""
    
    def __init__(self, api_key: str | None = None, model: str | None = None):
        import anthropic
        
        self.api_key = api_key or (
            settings.anthropic_api_key.get_secret_value()
            if settings.anthropic_api_key else None
        )
        self.model = model or settings.anthropic_model
        self.client = anthropic.AsyncAnthropic(api_key=self.api_key)
    
    def _convert_messages(self, messages: list[Message]) -> tuple[str | None, list[dict]]:
        """Convert messages to Anthropic format, extracting system message."""
        system = None
        result = []
        
        for msg in messages:
            if msg.role == Role.SYSTEM:
                system = msg.content
            elif msg.role == Role.TOOL:
                result.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.tool_call_id,
                            "content": msg.content,
                        }
                    ],
                })
            else:
                result.append({
                    "role": msg.role.value,
                    "content": msg.content,
                })
        
        return system, result
    
    def _convert_tools(self, tools: list[ToolDefinition]) -> list[dict]:
        """Convert tools to Anthropic format."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.parameters,
            }
            for tool in tools
        ]
    
    async def generate(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stop: list[str] | None = None,
    ) -> GenerationResult:
        """Generate a response using Anthropic API."""
        system, conv_messages = self._convert_messages(messages)
        
        kwargs = {
            "model": self.model,
            "messages": conv_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = self._convert_tools(tools)
        if stop:
            kwargs["stop_sequences"] = stop
        
        response = await self.client.messages.create(**kwargs)
        
        content = None
        tool_calls = []
        
        for block in response.content:
            if block.type == "text":
                content = block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input,
                ))
        
        return GenerationResult(
            content=content,
            tool_calls=tool_calls,
            finish_reason=response.stop_reason or "end_turn",
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
            total_tokens=response.usage.input_tokens + response.usage.output_tokens,
        )
    
    async def generate_stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stop: list[str] | None = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming response using Anthropic API."""
        system, conv_messages = self._convert_messages(messages)
        
        kwargs = {
            "model": self.model,
            "messages": conv_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = self._convert_tools(tools)
        if stop:
            kwargs["stop_sequences"] = stop
        
        async with self.client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text
    
    def count_tokens(self, text: str) -> int:
        """Approximate token count for Anthropic (uses tiktoken as approximation)."""
        try:
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except Exception:
            # Rough approximation: 4 chars per token
            return len(text) // 4


class LocalProvider(ModelProvider):
    """Local model provider via vLLM-compatible API."""
    
    def __init__(self, base_url: str | None = None, model: str | None = None):
        self.base_url = base_url or settings.local_model_url
        self.model = model or settings.local_model_name
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=300.0)
    
    def _convert_messages(self, messages: list[Message]) -> list[dict]:
        """Convert messages to OpenAI-compatible format."""
        result = []
        for msg in messages:
            d = {"role": msg.role.value, "content": msg.content}
            if msg.name:
                d["name"] = msg.name
            result.append(d)
        return result
    
    async def generate(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stop: list[str] | None = None,
    ) -> GenerationResult:
        """Generate a response using local vLLM API."""
        payload = {
            "model": self.model,
            "messages": self._convert_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        if stop:
            payload["stop"] = stop
        
        response = await self.client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
        
        choice = data["choices"][0]
        message = choice["message"]
        
        return GenerationResult(
            content=message.get("content"),
            finish_reason=choice.get("finish_reason", "stop"),
            prompt_tokens=data.get("usage", {}).get("prompt_tokens", 0),
            completion_tokens=data.get("usage", {}).get("completion_tokens", 0),
            total_tokens=data.get("usage", {}).get("total_tokens", 0),
        )
    
    async def generate_stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stop: list[str] | None = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming response using local vLLM API."""
        payload = {
            "model": self.model,
            "messages": self._convert_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        
        if stop:
            payload["stop"] = stop
        
        async with self.client.stream("POST", "/chat/completions", json=payload) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        if chunk["choices"] and chunk["choices"][0]["delta"].get("content"):
                            yield chunk["choices"][0]["delta"]["content"]
                    except json.JSONDecodeError:
                        continue
    
    def count_tokens(self, text: str) -> int:
        """Approximate token count (uses tiktoken as approximation)."""
        try:
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except Exception:
            return len(text) // 4


class ModelGateway:
    """
    Unified gateway to all model providers.
    
    Handles provider selection, rate limiting, and logging.
    """
    
    def __init__(self, provider: str | None = None):
        self.provider_name = provider or settings.model_provider
        self._provider: ModelProvider | None = None
    
    @property
    def provider(self) -> ModelProvider:
        """Get or create the model provider."""
        if self._provider is None:
            if self.provider_name == "openai":
                self._provider = OpenAIProvider()
            elif self.provider_name == "anthropic":
                self._provider = AnthropicProvider()
            elif self.provider_name == "local":
                self._provider = LocalProvider()
            else:
                raise ValueError(f"Unknown provider: {self.provider_name}")
        return self._provider
    
    async def generate(
        self,
        role: str,  # "injector" or "solver"
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> GenerationResult:
        """
        Generate a response for an agent role.
        
        Args:
            role: "injector" or "solver"
            messages: Conversation history
            tools: Available tools
            temperature: Sampling temperature (default from settings)
            max_tokens: Max tokens to generate
        
        Returns:
            GenerationResult with content and/or tool calls
        """
        temperature = temperature if temperature is not None else settings.solver_temperature
        max_tokens = max_tokens or settings.solver_max_tokens
        
        logger.info(
            "Generating response",
            role=role,
            provider=self.provider_name,
            messages=len(messages),
            tools=len(tools) if tools else 0,
        )
        
        start_time = datetime.utcnow()
        result = await self.provider.generate(
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        logger.info(
            "Generation complete",
            role=role,
            duration_s=duration,
            tokens=result.total_tokens,
            tool_calls=len(result.tool_calls),
        )
        
        return result
    
    async def generate_stream(
        self,
        role: str,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming response."""
        temperature = temperature if temperature is not None else settings.solver_temperature
        max_tokens = max_tokens or settings.solver_max_tokens
        
        async for chunk in self.provider.generate_stream(
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield chunk
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        return self.provider.count_tokens(text)


# Global gateway instance
_gateway: ModelGateway | None = None


def get_model_gateway() -> ModelGateway:
    """Get the global model gateway instance."""
    global _gateway
    if _gateway is None:
        _gateway = ModelGateway()
    return _gateway
