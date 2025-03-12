import os
import asyncio
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

# Import the Anthropic async client
from anthropic import AsyncAnthropic
from dotenv import load_dotenv
# Import the Azure Web PubSub client from the preview package.
from azure.messaging.webpubsubservice import WebPubSubServiceClient

load_dotenv()
app = FastAPI()

# Allow CORS (adjust origins as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load environment variables
WEBPUBSUB_CONNECTION_STRING = os.getenv("WEBPUBSUB_CONNECTION_STRING")
if not WEBPUBSUB_CONNECTION_STRING:
    raise Exception("Please set the WEBPUBSUB_CONNECTION_STRING environment variable.")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise Exception("Please set the ANTHROPIC_API_KEY environment variable.")

# Define the hub name (must match your Azure Web PubSub configuration)
hub_name = "myhub"

# Create a Web PubSub client using the connection string.
webpubsub_client = WebPubSubServiceClient.from_connection_string(
    connection_string=WEBPUBSUB_CONNECTION_STRING,
    hub=hub_name
)

# Initialize the Anthropic async client.
anthropic_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)


async def stream_anthropic_updates(user_message: str):
    """
    Calls Anthropic's streaming API. For each delta event, it:
      1. Extracts the text using either the 'text' or 'content' attribute,
         or falls back to converting the delta to a string.
      2. Broadcasts the chunk via Azure Web PubSub.
      3. Yields the chunk in SSE format.
    """
    messages = [{"role": "user", "content": user_message}]
    stream = await anthropic_client.messages.create(
        model="claude-3-5-sonnet-20240620",  # Update as needed.
        max_tokens=1024,
        messages=messages,
        stream=True,
    )

    async for event in stream:
        # For both content_block_delta and message_delta, try to get the text.
        if event.type in ("content_block_delta", "message_delta"):
            # Try 'text', then 'content', then fallback to string conversion.
            chunk = getattr(event.delta, "text", None) or getattr(event.delta, "content", None)
            if chunk is None:
                chunk = str(event.delta)
            # Send the chunk via Web PubSub.
            webpubsub_client.send_to_all(
                message=chunk,
                content_type="text/plain"
            )
            yield f"data: {chunk}\n\n"
    # Yield a final event to indicate end of stream.
    yield "data: [END]\n\n"


@app.post("/stream")
async def stream_endpoint(request: Request):
    """
    Accepts a JSON payload with a "message" field and returns a streaming response
    that forwards Anthropic API responses.
    """
    data = await request.json()
    user_message = data.get("message")
    if not user_message:
        raise HTTPException(status_code=400, detail="Missing 'message' in request body")

    return StreamingResponse(stream_anthropic_updates(user_message), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
