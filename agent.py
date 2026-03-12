



import asyncio
import json
import logging
from typing import List
import edge_tts
from dotenv import load_dotenv
from livekit import agents, rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    room_io,
)
from livekit.agents import llm as lk_llm
from livekit.plugins import deepgram, noise_cancellation, openai, silero
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from tools import get_weather, search_web

load_dotenv(".env")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Conversation Cache (rolling text window for GPT context)
# ---------------------------------------------------------------------------
class ConversationCache:
    """Keeps a rolling text window so GPT-4o Mini always sees recent context."""

    def __init__(self, max_chars: int = 6000):
        self.buffer: List[str] = []
        self.max_chars = max_chars

    def add(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        self.buffer.append(text)
        self._trim()

    def context(self) -> str:
        return " ".join(self.buffer)

    def _trim(self) -> None:
        joined = " ".join(self.buffer)
        while len(joined) > self.max_chars and self.buffer:
            self.buffer.pop(0)
            joined = " ".join(self.buffer)

import threading

class LocalTTS:
    _lock = threading.Lock()
    def __init__(self, voice: str = "en-US-AriaNeural", rate: str = "+0%", volume: str = "+0%"):
        self.voice = voice
        self.rate = rate
        self.volume = volume
    async def _synth(self, text: str, path: str):
        await edge_tts.Communicate(text, voice=self.voice, rate=self.rate, volume=self.volume).save(path)
    def speak(self, text: str, path: str = "edge_tts_out.mp3"):
        if not text:
            return
        if not self._lock.acquire(blocking=False):
            return
        try:
            try:
                asyncio.run(self._synth(text, path))
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._synth(text, path))
                loop.close()
        finally:
            self._lock.release()
    def stop(self) -> None:
        pass

# ---------------------------------------------------------------------------
# Agent Definition (minimal - NO tools here, tools handled manually)
# ---------------------------------------------------------------------------
class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=AGENT_INSTRUCTION,
        )

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
server = AgentServer()

@server.rtc_session()
async def my_agent(ctx: agents.JobContext) -> None:
    """
    Pipeline:
      Live voice (mic) -> Deepgram Nova-3 STT (streaming) ->
      Rolling cache -> GPT-4o Mini (OpenAI LLM) -> Local TTS (pyttsx3)

    STT handled ONLY inside AgentSession (with VAD).
    LLM + TTS handled manually via user_input_transcribed event.
    NO session.generate_reply() - prevents built-in TTS pipeline.
    """

    logger.info("Agent session started for room %s", ctx.room.name)

    cache = ConversationCache()
    tts = LocalTTS()
    is_speaking = False
    llm_task = None

    # Our own GPT-4o Mini client (decoupled from AgentSession to avoid
    # triggering LiveKit's internal TTS pipeline)
    llm_client = openai.LLM(model="gpt-4o-mini")
    logger.debug("Initialized OpenAI LLM client: %s", llm_client.model)

    # -------------------------------------------------------------------------
    # STT ONLY inside AgentSession: Deepgram Nova-2 (native streaming)
    # NO LLM, NO TTS in session - prevents built-in voice pipeline
    # -------------------------------------------------------------------------
    session = AgentSession(
        stt=deepgram.STT(
            model="nova-3",
            language="en",
            interim_results=True,
            punctuate=True,
            smart_format=True,
        ),
        vad=silero.VAD.load(), # voice activity detector
    )

    # -------------------------------------------------------------------------
    # STT FINAL CALLBACK (user_input_transcribed event)
    # Only react on is_final=True transcripts
    # -------------------------------------------------------------------------
    @session.on("user_input_transcribed")
    def _on_user_input(ev) -> None:
        """Fired on every STT transcript event from Deepgram."""
        nonlocal llm_task, is_speaking
        try:
            transcript = (getattr(ev, "transcript", "") or "").strip()
            is_final = getattr(ev, "is_final", False)
            
            # Debug print to ensure event is firing
            print(f"DEBUG: STT Event - '{transcript}' (Final: {is_final})")
            
            # --- MODIFICATION START: Publish real-time transcription ---
            if transcript:
                async def _publish_transcription():
                    try:
                        payload = json.dumps({
                            "type": "transcription",
                            "text": transcript,
                            "is_final": is_final
                        })
                        await ctx.room.local_participant.publish_data(
                            payload=payload.encode("utf-8"),
                            topic="lk.transcription"
                        )
                        logger.info(f"Published transcription: {transcript[:20]}...")
                    except Exception as e:
                        logger.error(f"Failed to publish transcription: {e}")
                
                # Check if loop is running
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(_publish_transcription())
                except RuntimeError:
                    logger.error("No running event loop for publishing transcription")
            # --- MODIFICATION END ---

            # --- NEW: Barge-in detection & interruption ---
            if not is_final and transcript:
                # User started speaking while assistant might be speaking; interrupt TTS and LLM
                if is_speaking:
                    logger.info("Barge-in: interrupting TTS and cancelling LLM task")
                    try:
                        tts.stop()
                    except Exception:
                        pass
                    try:
                        if llm_task and not llm_task.done():
                            llm_task.cancel()
                    except Exception:
                        pass
                    # Assistant no longer speaking
                    is_speaking = False

            # Only process final transcripts (ignore interim)
            if is_final and transcript:
                logger.info("User said (Final): %s", transcript)
                # Dispatch to async handler
                try:
                    loop = asyncio.get_running_loop()
                    llm_task = loop.create_task(_handle_final_transcript(transcript))
                except RuntimeError:
                     logger.error("No running event loop for handling transcript")
                # Mirror user final transcript into chat stream so frontend shows it
                try:
                    loop = asyncio.get_running_loop()
                    async def _mirror_user_chat() -> None:
                        try:
                            await ctx.room.local_participant.send_text(transcript, topic="lk.chat")
                        except Exception:
                            pass
                    loop.create_task(_mirror_user_chat())
                except Exception:
                    pass
                
        except Exception as e:
            logger.exception(f"Error processing STT event: {e}")

    # -------------------------------------------------------------------------
    # ASYNC GPT + TTS PIPELINE (manual, no session.generate_reply)
    # -------------------------------------------------------------------------
    async def _handle_final_transcript(text: str) -> None:
        """
        Full pipeline for a final STT transcript:
        1) Update rolling conversation cache
        2) Build ChatContext for the LLM
        3) Call OpenAI LLM (streaming) with tool support
        4) Execute tool calls if any
        5) Aggregate reply text
        6) Add reply to cache
        7) Speak reply via local TTS
        """
        logger.debug("Handling final transcript: %r", text)

        try:
            # 1) Add user text to rolling cache
            cache.add(f"User: {text}")
            conversation_ctx = cache.context()
            logger.debug("Conversation context length: %d chars", len(conversation_ctx))

            # 2) Build ChatContext using LiveKit's LLM utilities
            chat_ctx = lk_llm.ChatContext(
                items=[
                    lk_llm.ChatMessage(
                        role="system",
                        content=[AGENT_INSTRUCTION, SESSION_INSTRUCTION],
                    ),
                    lk_llm.ChatMessage(
                        role="user",
                        content=[conversation_ctx],
                    ),
                ]
            )

            # 3) Call LLM with tool support
            async def _run_llm_with_tools() -> str:
                tools = [get_weather, search_web]
                # Safe tool mapping
                tool_map = {}
                for t in tools:
                    if hasattr(t, 'info') and hasattr(t.info, 'name'):
                        tool_map[t.info.name] = t
                    elif hasattr(t, 'name'): # Fallback for mock tools
                         tool_map[t.name] = t
                         
                tool_names = list(tool_map.keys())

                for attempt in range(3):
                    logger.debug(
                        "LLM call attempt=%d with tools=%s", attempt + 1, tool_names
                    )

                    try:
                        stream = llm_client.chat(chat_ctx=chat_ctx, tools=tools)
                        reply_parts: list[str] = []
                        tool_calls: dict[str, lk_llm.FunctionToolCall] = {}

                        async with stream:
                            async for chunk in stream:
                                if chunk.delta and chunk.delta.content:
                                    reply_parts.append(chunk.delta.content)
                                    try:
                                        await ctx.room.local_participant.publish_data(
                                            payload=json.dumps({
                                                "type": "agent_response_delta",
                                                "text": chunk.delta.content,
                                            }).encode("utf-8"),
                                            topic="agent_response_partial",
                                        )
                                    except Exception as e:
                                        logger.error(f"Failed to publish agent delta: {e}")

                                if chunk.delta and chunk.delta.tool_calls:
                                    for tc in chunk.delta.tool_calls:
                                        tool_calls[tc.call_id] = tc

                        reply = "".join(reply_parts).strip()
                        if reply:
                            return reply

                        if not tool_calls:
                            return ""

                        # 4) Execute tool calls
                        for call_id, tc in tool_calls.items():
                            fn = tool_map.get(tc.name)
                            out = ""
                            is_error = False
                            
                            if fn is None:
                                out = f"Unknown tool: {tc.name}"
                                is_error = True
                            else:
                                try:
                                    args = json.loads(tc.arguments or "{}")
                                    if not isinstance(args, dict):
                                        raise ValueError("Arguments must be JSON object")
                                    # Handle both async and sync tools if needed, assuming async for now
                                    result = await fn(**args)
                                    out = str(result)
                                except Exception as e:
                                    out = f"Tool error: {e}"
                                    is_error = True

                            chat_ctx.items.append(
                                lk_llm.FunctionCall(
                                    call_id=call_id,
                                    name=tc.name,
                                    arguments=tc.arguments or "{}",
                                )
                            )
                            chat_ctx.items.append(
                                lk_llm.FunctionCallOutput(
                                    call_id=call_id,
                                    name=tc.name,
                                    output=out,
                                    is_error=is_error,
                                )
                            )
                    except Exception as e:
                        logger.error(f"LLM streaming error: {e}")
                        return "I encountered an error processing your request."

                return ""

            # 5) Get final assistant reply
            reply = (await _run_llm_with_tools()).strip()
            logger.debug("LLM reply: %r", reply[:100] if reply else "(empty)")

            if not reply:
                logger.warning("LLM returned empty reply; skipping TTS")
                return
            
            # --- MODIFICATION START: Publish LLM Response IMMEDIATELY ---
            # Publish BEFORE TTS so user sees text even if audio fails
            async def _publish_response():
                try:
                    logger.info("Publishing agent response: %s", reply[:30])
                    await ctx.room.local_participant.publish_data(
                        payload=json.dumps({
                            "type": "agent_response",
                            "text": reply
                        }).encode("utf-8"),
                        topic="agent_response"
                    )
                except Exception as e:
                    logger.error(f"Failed to publish response: {e}")
            
            asyncio.create_task(_publish_response())
            # --- MODIFICATION END ---

            # Also mirror final reply to chat stream so frontend ChatTranscript shows it
            try:
                await ctx.room.local_participant.send_text(reply, topic="lk.chat")
            except Exception:
                pass

            # 6) Store assistant reply in cache
            cache.add(f"Assistant: {reply}")
            logger.info("Assistant: %s", reply)

            try:
                nonlocal is_speaking
                is_speaking = True
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, tts.speak, reply)
            except Exception:
                pass
            finally:
                is_speaking = False

        except Exception:
            logger.exception("Error handling final transcript")

    # -------------------------------------------------------------------------
    # START SESSION
    # -------------------------------------------------------------------------
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
                )
            )
        ),
    )

    logger.info("Agent session running. Listening for user speech...")
    try:
        await ctx.room.local_participant.publish_data(
            payload=(SESSION_INSTRUCTION or "Hello, how can I help you?").encode("utf-8"),
            reliable=True,
            topic="agent_response",
        )
    except Exception:
        pass

    # NO session.generate_reply() - all GPT->TTS handled manually via
    # user_input_transcribed event callback

if __name__ == "__main__":
    agents.cli.run_app(server)
