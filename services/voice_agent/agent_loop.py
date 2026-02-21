# services/voice_agent/agent_loop.py
# Main conversation loop.
# Pure orchestrator — no business logic here.
# Wires together: MemoryManager → DecisionEngine → ActionExecutor → MemoryManager

import sys
import os

# Make sure all modules are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'llm'))

from memory_manager import MemoryManager
from decision_engine import decide
from action_executor import execute
from constants import MAX_TURNS_PER_SESSION


def run_agent(session_id: str = "local_user"):
    """
    Starts an interactive text session.
    In production this will be called by conversation_controller.py
    with transcripts from STT instead of input().
    """
    memory = MemoryManager()

    # Always start a completely fresh state — never resume mid-session
    from conversation_state import ConversationState
    state = ConversationState(session_id=session_id)
    memory._cache[session_id] = state

    print()
    print("=" * 50)
    print("  Ration Ordering Agent")
    print("=" * 50)
    print("Agent: Hello! This is your monthly ration reminder.")
    print("Agent: What items would you like to order this month?")
    print("       (type 'bye' to exit, 'show cart' to see items)")
    print("=" * 50)
    print()

    while True:
        try:
            # ── Get input ─────────────────────────────────────────────────────
            user_input = input("You: ").strip()

            if not user_input:
                continue

            # ── Turn limit guard ──────────────────────────────────────────────
            if state.turn_count >= MAX_TURNS_PER_SESSION:
                print("Agent: We've reached the session limit. Please call again.")
                break

            # ── Save user turn to history ─────────────────────────────────────
            memory.add_history(state, "user", user_input)

            # ── Step 1: Classify intent ───────────────────────────────────────
            intent_result = decide(user_input, state)

            # ── Step 2: Execute and get response ─────────────────────────────
            response = execute(intent_result, state)

            # ── Step 3: Persist state ─────────────────────────────────────────
            memory.save_session(state)

            # ── Step 4: Handle exit ───────────────────────────────────────────
            if response == "__EXIT__":
                print("Agent: Thank you for your order. Goodbye!")
                break

            # ── Step 5: Print response and save to history ────────────────────
            print(f"Agent: {response}")
            print()
            memory.add_history(state, "agent", response)

        except KeyboardInterrupt:
            print("\nAgent: Session ended. Goodbye!")
            break

        except Exception as e:
            print(f"Agent: Sorry, something went wrong. Please try again.")
            print(f"[DEBUG] {type(e).__name__}: {e}")


if __name__ == "__main__":
    run_agent()

