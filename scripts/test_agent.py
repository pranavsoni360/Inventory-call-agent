from services.voice_agent.agent_loop import AgentLoop

agent = AgentLoop()
session = "test123"

while True:
    user = input("User: ")
    reply = agent.handle_input(session, user)

    if reply is None:
        print("Conversation ended.")
        break

    print("Agent:", reply)
