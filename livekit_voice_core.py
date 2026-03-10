import asyncio
from dotenv import load_dotenv
from livekit import agents, rtc
from livekit.agents import Agent, AgentServer, AgentSession, room_io
from livekit.plugins import noise_cancellation, openai

from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from tools import get_weather, search_web

load_dotenv(".env")

# ---------------------------------------------------------------------------
# COST CONFIG (GPT-4o-mini pricing)
# ---------------------------------------------------------------------------
INPUT_COST_PER_TOKEN = 0.15 / 1_000_000
OUTPUT_COST_PER_TOKEN = 0.60 / 1_000_000


def log_usage_and_cost(usage) -> None:
    """Print token usage and estimated cost (if usage is available)."""
    if not usage:
        return

    input_tokens = getattr(usage, "prompt_tokens", None)
    output_tokens = getattr(usage, "completion_tokens", None)
    total_tokens = getattr(usage, "total_tokens", None)

    if input_tokens is None or output_tokens is None or total_tokens is None:
        return

    input_cost = input_tokens * INPUT_COST_PER_TOKEN
    output_cost = output_tokens * OUTPUT_COST_PER_TOKEN
    total_cost = input_cost + output_cost

    print("\n===== OPENAI USAGE =====")
    print(f"Input tokens:  {input_tokens}")
    print(f"Output tokens: {output_tokens}")
    print(f"Total tokens:  {total_tokens}")
    print("===== COST (USD) =====")
    print(f"Input cost:  ${input_cost:.8f}")
    print(f"Output cost: ${output_cost:.8f}")
    print(f"Total cost:  ${total_cost:.8f}")
    print("========================\n")


# ---------------------------------------------------------------------------
# LiveKit Agent definition
# ---------------------------------------------------------------------------


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=AGENT_INSTRUCTION,
            tools=[get_weather, search_web],
        )


server = AgentServer()


@server.rtc_session()
async def my_agent(ctx: agents.JobContext) -> None:
    """Triggered when a participant joins a LiveKit room."""

    print("[livekit_voice_core] my_agent: job assigned, room:", ctx.room.name)

    # OpenAI chat LLM driving the voice agent (text only; browser handles free TTS).
    llm = openai.LLM(
        model="gpt-4.1-mini",
    )
    session = AgentSession(llm=llm)

    # Debug: log user transcripts to verify STT is receiving mic audio.
    def _on_user_input(ev: agents.UserInputTranscribedEvent) -> None:
        try:
            print(
                "[livekit_voice_core] user_input_transcribed:",
                repr(ev.transcript),
                "final=",
                getattr(ev, "is_final", False),
            )
        except Exception:
            pass

    session.on("user_input_transcribed", _on_user_input)

    try:
        await session.start(
            room=ctx.room,
            agent=Assistant(),
            room_options=room_io.RoomOptions(
                audio_input=room_io.AudioInputOptions(
                    noise_cancellation=lambda params: (
                        noise_cancellation.BVCTelephony()
                        if params.participant.kind
                        == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                        else noise_cancellation.BVC()
                    ),
                ),
            ),
        )
        print("[livekit_voice_core] session.start() completed")
    except Exception as e:
        import traceback

        print("[livekit_voice_core] ERROR during session.start():", e)
        traceback.print_exc()
        raise

    async def _safe_publish(text: str) -> None:
        try:
            await ctx.room.local_participant.publish_data(
                payload=text.encode("utf-8"),
                reliable=True,
                topic="agent_response",
            )
            print("[livekit_voice_core] data published:", repr(text))
        except Exception as e:
            import traceback
            print("[livekit_voice_core] publish_data failed:", e)
            traceback.print_exc()

    try:
        await asyncio.sleep(0.5)
        await _safe_publish(SESSION_INSTRUCTION or "Hello, how can I help you?")
    except Exception:
        pass


def main() -> None:
    """CLI entrypoint to run the LiveKit voice agent server."""
    agents.cli.run_app(server)


if __name__ == "__main__":
    main()
