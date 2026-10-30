import asyncio
import os

from providers.base import ChatMessage
from providers.openai_provider import OpenAIProvider


async def main():
    provider = OpenAIProvider(api_key=os.environ["OPENAI_API_KEY"])

    vectors = await provider.embed(["hello world"])
    print("embed:", len(vectors), "vector(s) of length", len(vectors[0]))

    print("stream: ", end="")
    async for token in provider.stream([ChatMessage(role="user", content="Say one word")]):
        print(token, end="", flush=True)
    print()

    result = await provider.complete([ChatMessage(role="user", content="Say one word")])
    print("complete:", result)


asyncio.run(main())