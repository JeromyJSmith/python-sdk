import anyio
import click
import mcp.types as types
from mcp.server import Server


@click.group()
def cli():
    pass


@cli.command()
@click.option("--port", default=8000, help="Port to listen on for SSE")
@click.option(
    "--transport",
    type=click.Choice(["stdio", "sse"]),
    default="stdio",
    help="Transport type",
)
def main(port: int, transport: str) -> int:
    return anyio.run(_amain, port, transport)


def create_messages(
    context: str | None = None, topic: str | None = None
) -> list[types.PromptMessage]:
    """Create the messages for the prompt."""
    messages = []

    # Add context if provided
    if context:
        messages.append(
            types.PromptMessage(
                role="user",
                content=types.TextContent(
                    type="text", text=f"Here is some relevant context: {context}"
                ),
            )
        )

    # Add the main prompt
    prompt = "Please help me with "
    if topic:
        prompt += f"the following topic: {topic}"
    else:
        prompt += "whatever questions I may have."

    messages.append(
        types.PromptMessage(
            role="user", content=types.TextContent(type="text", text=prompt)
        )
    )

    return messages


async def _amain(port: int, transport: str) -> int:
    app = Server("mcp-simple-prompt")

    @app.list_prompts()
    async def list_prompts() -> list[types.Prompt]:
        return [
            types.Prompt(
                name="simple",
                description="A simple prompt that can take optional context and topic "
                           "arguments",
                arguments=[
                    types.PromptArgument(
                        name="context",
                        description="Additional context to consider",
                        required=False,
                    ),
                    types.PromptArgument(
                        name="topic",
                        description="Specific topic to focus on",
                        required=False,
                    ),
                ],
            )
        ]

    @app.get_prompt()
    async def get_prompt(
        name: str, arguments: dict[str, str] | None = None
    ) -> types.GetPromptResult:
        if name != "simple":
            raise ValueError(f"Unknown prompt: {name}")

        if arguments is None:
            arguments = {}

        return types.GetPromptResult(
            messages=create_messages(
                context=arguments.get("context"), topic=arguments.get("topic")
            ),
            description="A simple prompt with optional context and topic arguments",
        )

    if transport == "sse":
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Route

        sse = SseServerTransport("/messages")

        async def handle_sse(scope, receive, send):
            async with sse.connect_sse(scope, receive, send) as streams:
                await app.run(
                    streams[0], streams[1], app.create_initialization_options()
                )

        async def handle_messages(scope, receive, send):
            await sse.handle_post_message(scope, receive, send)

        starlette_app = Starlette(
            debug=True,
            routes=[
                Route("/sse", endpoint=handle_sse),
                Route("/messages", endpoint=handle_messages, methods=["POST"]),
            ],
        )

        import uvicorn

        uvicorn.run(starlette_app, host="0.0.0.0", port=port)
    else:
        from mcp.server.stdio import stdio_server

        async with stdio_server() as streams:
            await app.run(streams[0], streams[1], app.create_initialization_options())

    return 0