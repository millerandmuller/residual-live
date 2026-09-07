from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

agent = LlmAgent(
    name="test_agent",
    model="gemini-3.5-flash",
    instruction="Say hello and echo the user."
)

runner = Runner(
    agent=agent,
    app_name="test_app",
    session_service=InMemorySessionService(),
    auto_create_session=True
)

events = runner.run(
    user_id="user1",
    session_id="sess1",
    new_message=types.Content(parts=[types.Part.from_text(text="Hi there!")])
)

for e in events:
    print(type(e), getattr(e, "message", None), getattr(e, "content", None))
