from google.adk.agents.base_agent import BaseAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types


async def run_agent_once(
    agent: BaseAgent,
    user_text: str,
    *,
    app_name: str,
    session_id: str,
    user_id: str = "system",
    state: dict | None = None,
) -> str:
    """Runs a single ADK agent end-to-end against one text input in a fresh,
    isolated session and returns its final response text. Used for the
    technical producer and director agents, which each run as one
    self-contained step rather than sharing session state across the graph.
    """
    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name=app_name, user_id=user_id, session_id=session_id, state=state or {}
    )
    runner = Runner(agent=agent, app_name=app_name, session_service=session_service)
    content = types.Content(role="user", parts=[types.Part(text=user_text)])

    final_text: str | None = None
    async for event in runner.run_async(
        user_id=user_id, session_id=session_id, new_message=content
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = event.content.parts[0].text

    if final_text is None:
        raise RuntimeError(f"Agent '{agent.name}' produced no final response.")
    return final_text
