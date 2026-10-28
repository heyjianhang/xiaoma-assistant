"""LangChain adapter preserving the gateway's non-standard reasoning_content field.

The parent retains parsing, SDK streaming, tool calls, usage and model profiles.
Only provider-returned reasoning text is added; it is never inferred from answers.
"""

from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_openai import ChatOpenAI


class GatewayChatOpenAI(ChatOpenAI):
    def _convert_chunk_to_generation_chunk(self, chunk, default_chunk_class, base_generation_info):
        result = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        choices = chunk.get("choices") or chunk.get("chunk", {}).get("choices", [])
        if result is not None and choices and isinstance(result.message, AIMessageChunk):
            value = (choices[0].get("delta") or {}).get("reasoning_content")
            if isinstance(value, str) and value:
                result.message.additional_kwargs["reasoning_content"] = value
        return result

    def _create_chat_result(self, response, generation_info=None):
        result = super()._create_chat_result(response, generation_info)
        body = response if isinstance(response, dict) else response.model_dump()
        for generation, choice in zip(result.generations, body.get("choices", []), strict=False):
            value = (choice.get("message") or {}).get("reasoning_content")
            if isinstance(generation.message, AIMessage) and isinstance(value, str) and value:
                generation.message.additional_kwargs["reasoning_content"] = value
        return result


def reasoning_text(message):
    value = getattr(message, "additional_kwargs", {}).get("reasoning_content")
    if isinstance(value, str) and value:
        return value
    content = getattr(message, "content", "")
    if isinstance(content, list):
        return "".join(
            p.get("reasoning", p.get("text", ""))
            for p in content
            if isinstance(p, dict)
            and p.get("type") == "reasoning"
            and isinstance(p.get("reasoning", p.get("text", "")), str)
        )
    return ""
