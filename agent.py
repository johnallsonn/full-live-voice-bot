# # agents → core LiveKit agent framework
# # rtc → real-time communication primitives
# # AgentServer → HTTP + RTC server
# # AgentSession → one live conversation session
# # Agent → base AI agent class
# # room_io → audio/video input options
# # openai → realtime OpenAI speech + LLM
# # noise_cancellation → clean incoming audio

# from dotenv import load_dotenv
# import os
# from livekit import agents, rtc
# from livekit.agents import AgentServer, AgentSession, Agent, room_io
# from livekit.plugins import (
#     openai,
#     noise_cancellation,
# )
# from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
# from tools import get_weather, search_web

# load_dotenv(".env")
# class Assistant(Agent):
#     def __init__(self) -> None:
#         super().__init__(
#             instructions=AGENT_INSTRUCTION,
#             tools=[get_weather, search_web]
#             )

# server = AgentServer()#Creating the Server - just configuration
# #async for Audio streaming,LLM streaming,Tool calls, Network IO
# @server.rtc_session()
# async def my_agent(ctx: agents.JobContext):# triggered when participant joins a LiveKit room
#     session = AgentSession(
#              llm=openai.realtime.RealtimeModel(voice="marin"),#voice="marin" → TTS voice
#     )
#     await session.start(                #Opens WebSocket to OpenAI for streaming
#         room=ctx.room,                 #Attach session to LiveKit room
#         agent=Assistant(),
#         room_options=room_io.RoomOptions(
#             audio_input=room_io.AudioInputOptions(      #configures how incoming audio is processed.
#                 noise_cancellation=lambda params: noise_cancellation.BVCTelephony() if params.participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP else noise_cancellation.BVC(),
#             ),
#         ),
#     )
#     await session.generate_reply(        # AI speaks first
#         instructions=SESSION_INSTRUCTION
#     )
# if __name__ == "__main__":
#     agents.cli.run_app(server)   #Runs HTTP + RTC server














# LiveKit Agent with free local TTS (pyttsx3) and basic interrupt handling.
# - OpenAI Realtime is used only as the LLM (no OpenAI TTS / no tts-1).
# - Agent text replies are sent over LiveKit "lk.chat" and spoken locally via pyttsx3.
# - When a new agent message arrives, any current speech is interrupted and the new text is spoken.
# LiveKit Agent with free local TTS (pyttsx3) and basic interrupt handling.
# - OpenAI Realtime is used only as the LLM (no OpenAI TTS / no tts-1).
# - Agent text replies are sent over LiveKit "lk.chat" and spoken locally via pyttsx3.
# - When a new agent message arrives, any current speech is interrupted
#   and only the latest text is spoken.
# LiveKit Agent with free local TTS (pyttsx3) and basic interrupt handling.
# - OpenAI Realtime is used only as the LLM (no OpenAI TTS / no tts-1).
# - Agent text replies are delivered via LiveKit and spoken locally via pyttsx3.
# - When a new agent message arrives, current speech is interrupted and
#   only the latest text is spoken.













# import asyncio #Used to run non-blocking background tasks (important for LiveKit + TTS)
# import logging
# import queue
# import threading
# import pyttsx3 #free TTS engine
# from dotenv import load_dotenv
# from livekit import agents, rtc
# from livekit.agents import (
#     Agent,
#     AgentServer,# runs the agent app
#     AgentSession,#one conversation session per user/room
#     room_io,#audio/text I/O configuration
#     MetricsCollectedEvent,
#     metrics,#token, latency, usage tracking
# )
# from livekit.plugins import noise_cancellation, openai
# from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
# from tools import get_weather, search_web

# load_dotenv(".env")
# logger = logging.getLogger(__name__)

# # ---------------------------------------------------------------------------
# # Local TTS (pyttsx3) with simple interrupt-on-new-message behavior
# # ---------------------------------------------------------------------------
# _tts_engine = pyttsx3.init()
# _tts_queue: "queue.Queue[str]" = queue.Queue()#Thread-safe queue to send text to TTS worker
# _tts_thread: threading.Thread | None = None
# _tts_lock = threading.Lock()

# def _tts_worker() -> None:
#     """Background worker that consumes text from _tts_queue and speaks it."""
#     while True:
#         text = _tts_queue.get()
#         if text is None:
#             # Sentinel to shut down worker (not used in normal flow)
#             break

#         # Stop any previous speech before starting new one.
#         try:
#             _tts_engine.stop()
#         except Exception:
#             pass

#         try:
#             _tts_engine.say(text)
#             _tts_engine.runAndWait()
#         except Exception:
#             # Don't let TTS errors crash the agent loop
#             continue

# def speak_text_interruptible(text: str) -> None:
#     """Interrupt any current speech and speak `text` next."""
#     global _tts_thread

#     with _tts_lock:
#         # Lazily start worker thread
#         if _tts_thread is None or not _tts_thread.is_alive():
#             _tts_thread = threading.Thread(target=_tts_worker, daemon=True)
#             _tts_thread.start()

#         # Drop any queued items so we only speak the latest text
#         try:
#             while True:
#                 _tts_queue.get_nowait()
#         except queue.Empty:
#             pass

#         # Stop current utterance and enqueue new one
#         try:
#             _tts_engine.stop()
#         except Exception:
#             pass

#         _tts_queue.put(text)

# # ---------------------------------------------------------------------------
# # LiveKit Agent definition
# # ---------------------------------------------------------------------------

# class Assistant(Agent):
#     def __init__(self) -> None:
#         super().__init__(
#             instructions=AGENT_INSTRUCTION,
#             tools=[get_weather, search_web],
#         )
# server = AgentServer()

# @server.rtc_session()
# async def my_agent(ctx: agents.JobContext) -> None:
#     """Triggered when a participant joins a LiveKit room."""

#     # --- Local TTS hook on a text stream (if available) --------------------
#     def _on_chat(reader, participant_identity: str) -> None:
#         async def _read_all() -> None: #Async reader task
#             try:
#                 text = await reader.read_all()
#             except Exception:
#                 return

#             speak_text_interruptible(text)

#         asyncio.create_task(_read_all())

#     ctx.room.register_text_stream_handler("lk.chat", _on_chat)

#     # --- Configure LLM: use GPT‑4o mini Realtime ---------------------------
#     #
#     # Model name comes from OpenAI's GPT‑4o mini Realtime docs.
#     llm = openai.realtime.RealtimeModel(
#         model="gpt-4o-mini-realtime-preview",
#     )

#     session = AgentSession(
#         llm=llm,
#     )

#     # --- Metrics + token & cost logging -----------------------------------
#     #
#     # Collect usage for this session and log an estimated USD cost using
#     # OpenAI's gpt-4o-mini-realtime pricing (per 1M tokens).
#     usage_collector = metrics.UsageCollector()#Collects tokens & latency

#     @session.on("metrics_collected")
#     def _on_metrics_collected(ev: MetricsCollectedEvent) -> None:
#         # Log detailed metrics (tokens, ttft, etc.) via LiveKit helper
#         metrics.log_metrics(ev.metrics)
#         # Accumulate into UsageCollector summary
#         usage_collector.collect(ev.metrics)

#     async def _log_usage() -> None:
#         summary = usage_collector.get_summary()

#         # Short aliases for clarity
#         text_in = summary.llm_input_text_tokens
#         text_in_cached = summary.llm_input_cached_text_tokens
#         audio_in = summary.llm_input_audio_tokens
#         audio_in_cached = summary.llm_input_cached_audio_tokens
#         text_out = summary.llm_output_text_tokens
#         audio_out = summary.llm_output_audio_tokens

#         # Separate uncached from cached
#         text_in_uncached = max(text_in - text_in_cached, 0)
#         audio_in_uncached = max(audio_in - audio_in_cached, 0)

#         # Prices for gpt-4o-mini-realtime-preview (USD per 1M tokens)
#         TEXT_INPUT_PRICE = 0.60
#         TEXT_CACHED_INPUT_PRICE = 0.30
#         TEXT_OUTPUT_PRICE = 2.40
#         AUDIO_INPUT_PRICE = 10.00
#         AUDIO_CACHED_INPUT_PRICE = 0.30
#         AUDIO_OUTPUT_PRICE = 20.00

#         # Cost estimation (all token counts are plain token counts)
#         cost_text_in = (
#             text_in_uncached * TEXT_INPUT_PRICE
#             + text_in_cached * TEXT_CACHED_INPUT_PRICE
#         ) / 1_000_000.0

#         cost_audio_in = (
#             audio_in_uncached * AUDIO_INPUT_PRICE
#             + audio_in_cached * AUDIO_CACHED_INPUT_PRICE
#         ) / 1_000_000.0

#         cost_text_out = text_out * TEXT_OUTPUT_PRICE / 1_000_000.0
#         cost_audio_out = audio_out * AUDIO_OUTPUT_PRICE / 1_000_000.0

#         total_cost = cost_text_in + cost_audio_in + cost_text_out + cost_audio_out

#         logger.info(
#             "LLM usage summary: %s | estimated gpt-4o-mini-realtime cost: "
#             "total=$%.6f (text_in=$%.6f, text_out=$%.6f, audio_in=$%.6f, audio_out=$%.6f)",
#             summary,
#             total_cost,
#             cost_text_in,
#             cost_text_out,
#             cost_audio_in,
#             cost_audio_out,
#         )

#     # Log usage once the session ends; does not change agent behavior.
#     ctx.add_shutdown_callback(_log_usage)

#     # --- Start LiveKit AgentSession ---------------------------------------
#     await session.start(#Joins room & Activates agent

#         room=ctx.room,
#         agent=Assistant(),
#         room_options=room_io.RoomOptions(
#             audio_input=room_io.AudioInputOptions(
#                 noise_cancellation=lambda params: (
#                     noise_cancellation.BVCTelephony()
#                     if params.participant.kind
#                     == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
#                     else noise_cancellation.BVC()
#                 ),
#             ),
#         ),
#     )

#     # Initial greeting from the agent (text only; TTS handled locally).
#     await session.generate_reply(
#         instructions=SESSION_INSTRUCTION,
#     )

# if __name__ == "__main__":
#     agents.cli.run_app(server)







# from dotenv import load_dotenv
# import os
# from livekit import agents, rtc
# from livekit.agents import AgentServer, AgentSession, Agent, room_io
# from livekit.plugins import (
#     openai,
#     noise_cancellation,
# )
#
# from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
# from tools import get_weather, search_web
#
# load_dotenv(".env")
#
# class Assistant(Agent):
#     def __init__(self) -> None:
#         super().__init__(
#             instructions=AGENT_INSTRUCTION,
#             tools=[get_weather, search_web]
#             )
#
# server = AgentServer()
#
# # AZURE_OPENAI_API_KEY=os.getenv("AZURE_OPENAI_API_KEY")
#
# @server.rtc_session()
# async def my_agent(ctx: agents.JobContext):
#     session = AgentSession(
#         llm=openai.realtime.RealtimeModel(voice="marin"),
#
#     )
#
#     await session.start(
#         room=ctx.room,
#         agent=Assistant(),
#         room_options=room_io.RoomOptions(
#             audio_input=room_io.AudioInputOptions(
#                 noise_cancellation=lambda params: noise_cancellation.BVCTelephony() if params.participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP else noise_cancellation.BVC(),
#             ),
#         ),
#     )
#
#     await session.generate_reply(
#         instructions=SESSION_INSTRUCTION
#     )
#
#
# if __name__ == "__main__":
#     agents.cli.run_app(server)












# import asyncio
# import logging
# import os
# import queue
# import threading
# import tempfile
# import wave

# import pyttsx3
# import whisper
# from dotenv import load_dotenv
# from openai import OpenAI

# from livekit import agents, rtc
# from livekit.agents import AgentServer

# from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION

# # --------------------------------------------------
# # ENV + LOGGING
# # --------------------------------------------------
# load_dotenv(".env")
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# # --------------------------------------------------
# # OPENAI CLIENT (GPT-4o-mini = cheapest good LLM)
# # --------------------------------------------------
# openai_client = OpenAI()

# # --------------------------------------------------
# # LOCAL WHISPER (FREE STT)
# # --------------------------------------------------
# logger.info("Loading Whisper model...")
# whisper_model = whisper.load_model("base")  # tiny / base / small

# # --------------------------------------------------
# # LOCAL TTS (FREE)
# # --------------------------------------------------
# _tts_engine = pyttsx3.init()
# _tts_queue: "queue.Queue[str]" = queue.Queue()
# _tts_thread: threading.Thread | None = None
# _tts_lock = threading.Lock()


# def _tts_worker():
#     while True:
#         text = _tts_queue.get()
#         if text is None:
#             break

#         try:
#             _tts_engine.stop()
#             _tts_engine.say(text)
#             _tts_engine.runAndWait()
#         except Exception:
#             continue


# def speak_interruptible(text: str):
#     global _tts_thread

#     with _tts_lock:
#         if _tts_thread is None or not _tts_thread.is_alive():
#             _tts_thread = threading.Thread(target=_tts_worker, daemon=True)
#             _tts_thread.start()

#         # Clear queue
#         while not _tts_queue.empty():
#             try:
#                 _tts_queue.get_nowait()
#             except queue.Empty:
#                 break

#         try:
#             _tts_engine.stop()
#         except Exception:
#             pass

#         _tts_queue.put(text)


# # --------------------------------------------------
# # AGENT SERVER
# # --------------------------------------------------
# server = AgentServer()


# @server.rtc_session()
# async def my_agent(ctx: agents.JobContext):
#     room = ctx.room

#     async def process_audio_track(track: rtc.Track):
#         if track.kind != rtc.TrackKind.KIND_AUDIO:
#             return

#         logger.info("Audio track subscribed")

#         audio_stream = rtc.AudioStream(track)

#         pcm_bytes = bytearray()
#         sample_rate = 16000
#         channels = 1

#         async for frame in audio_stream:
#             pcm_bytes.extend(frame.data)

#             # ~6 seconds max
#             if getattr(frame, "timestamp", 0) > 6000:
#                 break

#         await audio_stream.aclose()

#         if not pcm_bytes:
#             logger.info("No audio received")
#             return

#         # --------------------------------------------------
#         # WRITE WAV USING BUILT-IN WAVE (NO soundfile)
#         # --------------------------------------------------
#         with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
#             wav_path = f.name

#         with wave.open(wav_path, "wb") as wf:
#             wf.setnchannels(channels)
#             wf.setsampwidth(2)  # 16-bit PCM
#             wf.setframerate(sample_rate)
#             wf.writeframes(pcm_bytes)

#         try:
#             result = whisper_model.transcribe(wav_path)
#         finally:
#             try:
#                 os.remove(wav_path)
#             except OSError:
#                 pass

#         user_text = (result.get("text") or "").strip()
#         if not user_text:
#             logger.info("Empty transcription")
#             return

#         logger.info("User: %s", user_text)

#         completion = openai_client.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[
#                 {"role": "system", "content": AGENT_INSTRUCTION},
#                 {"role": "user", "content": user_text},
#             ],
#             temperature=0.6,
#         )

#         reply = completion.choices[0].message.content
#         logger.info("Assistant: %s", reply)

#         speak_interruptible(reply)

#         try:
#             await room.local_participant.send_text(reply, topic="lk.chat")
#         except Exception:
#             pass


# # --------------------------------------------------
# # ENTRY POINT
# # --------------------------------------------------
# if __name__ == "__main__":
#     agents.cli.run_app(server)







# import asyncio
# import logging
# import queue
# import threading
# import pyttsx3
# from dotenv import load_dotenv
# from livekit import agents, rtc
# from livekit.agents import (
#     Agent,
#     AgentServer,
#     AgentSession,
#     room_io,
#     MetricsCollectedEvent,
#     metrics,
# )
# from livekit.plugins import noise_cancellation, openai
# from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
# from tools import get_weather, search_web

# load_dotenv(".env")
# logger = logging.getLogger(__name__)

# # ---------------------------------------------------------------------------
# # Local TTS (pyttsx3) with simple interrupt-on-new-message behavior
# # ---------------------------------------------------------------------------
# _tts_engine = pyttsx3.init()
# _tts_queue: "queue.Queue[str]" = queue.Queue()
# _tts_thread: threading.Thread | None = None
# _tts_lock = threading.Lock()

# def _tts_worker() -> None:
#     """Background worker that consumes text from _tts_queue and speaks it."""
#     while True:
#         text = _tts_queue.get()
#         if text is None:
#             # Sentinel to shut down worker (not used in normal flow)
#             break

#         # Stop any previous speech before starting new one.
#         try:
#             _tts_engine.stop()
#         except Exception:
#             pass

#         try:
#             _tts_engine.say(text)
#             _tts_engine.runAndWait()
#         except Exception:
#             # Don't let TTS errors crash the agent loop
#             continue

# def speak_text_interruptible(text: str) -> None:
#     """Interrupt any current speech and speak `text` next."""
#     global _tts_thread

#     with _tts_lock:
#         # Lazily start worker thread
#         if _tts_thread is None or not _tts_thread.is_alive():
#             _tts_thread = threading.Thread(target=_tts_worker, daemon=True)
#             _tts_thread.start()

#         # Drop any queued items so we only speak the latest text
#         try:
#             while True:
#                 _tts_queue.get_nowait()
#         except queue.Empty:
#             pass

#         # Stop current utterance and enqueue new one
#         try:
#             _tts_engine.stop()
#         except Exception:
#             pass

#         _tts_queue.put(text)

# # ---------------------------------------------------------------------------
# # LiveKit Agent definition
# # ---------------------------------------------------------------------------

# class Assistant(Agent):
#     def __init__(self) -> None:
#         super().__init__(
#             instructions=AGENT_INSTRUCTION,
#             tools=[get_weather, search_web],
#         )
# server = AgentServer()

# @server.rtc_session()
# async def my_agent(ctx: agents.JobContext) -> None:
#     """Triggered when a participant joins a LiveKit room."""

#     # --- Local TTS hook on a text stream (if available) --------------------
#     def _on_chat(reader, participant_identity: str) -> None:
#         async def _read_all() -> None:
#             try:
#                 text = await reader.read_all()
#             except Exception:
#                 return

#             speak_text_interruptible(text)

#         asyncio.create_task(_read_all())

#     ctx.room.register_text_stream_handler("lk.chat", _on_chat)

#     # --- Configure LLM: use GPT‑4o mini Realtime ---------------------------
#     #
#     # Model name comes from OpenAI's GPT‑4o mini Realtime docs.
#     llm = openai.realtime.RealtimeModel(
#         model="gpt-4o-mini-realtime-preview",
#     )

#     session = AgentSession(
#         llm=llm,
#     )

#     # --- Metrics + token & cost logging -----------------------------------
#     #
#     # Collect usage for this session and log an estimated USD cost using
#     # OpenAI's gpt-4o-mini-realtime pricing (per 1M tokens).
#     usage_collector = metrics.UsageCollector()

#     @session.on("metrics_collected")
#     def _on_metrics_collected(ev: MetricsCollectedEvent) -> None:
#         # Log detailed metrics (tokens, ttft, etc.) via LiveKit helper
#         metrics.log_metrics(ev.metrics)
#         # Accumulate into UsageCollector summary
#         usage_collector.collect(ev.metrics)

#     async def _log_usage() -> None:
#         summary = usage_collector.get_summary()

#         # Short aliases for clarity
#         text_in = summary.llm_input_text_tokens
#         text_in_cached = summary.llm_input_cached_text_tokens
#         audio_in = summary.llm_input_audio_tokens
#         audio_in_cached = summary.llm_input_cached_audio_tokens
#         text_out = summary.llm_output_text_tokens
#         audio_out = summary.llm_output_audio_tokens

#         # Separate uncached from cached
#         text_in_uncached = max(text_in - text_in_cached, 0)
#         audio_in_uncached = max(audio_in - audio_in_cached, 0)

#         # Prices for gpt-4o-mini-realtime-preview (USD per 1M tokens)
#         TEXT_INPUT_PRICE = 0.60
#         TEXT_CACHED_INPUT_PRICE = 0.30
#         TEXT_OUTPUT_PRICE = 2.40
#         AUDIO_INPUT_PRICE = 10.00
#         AUDIO_CACHED_INPUT_PRICE = 0.30
#         AUDIO_OUTPUT_PRICE = 20.00

#         # Cost estimation (all token counts are plain token counts)
#         cost_text_in = (
#             text_in_uncached * TEXT_INPUT_PRICE
#             + text_in_cached * TEXT_CACHED_INPUT_PRICE
#         ) / 1_000_000.0

#         cost_audio_in = (
#             audio_in_uncached * AUDIO_INPUT_PRICE
#             + audio_in_cached * AUDIO_CACHED_INPUT_PRICE
#         ) / 1_000_000.0

#         cost_text_out = text_out * TEXT_OUTPUT_PRICE / 1_000_000.0
#         cost_audio_out = audio_out * AUDIO_OUTPUT_PRICE / 1_000_000.0

#         total_cost = cost_text_in + cost_audio_in + cost_text_out + cost_audio_out

#         logger.info(
#             "LLM usage summary: %s | estimated gpt-4o-mini-realtime cost: "
#             "total=$%.6f (text_in=$%.6f, text_out=$%.6f, audio_in=$%.6f, audio_out=$%.6f)",
#             summary,
#             total_cost,
#             cost_text_in,
#             cost_text_out,
#             cost_audio_in,
#             cost_audio_out,
#         )

#     # Log usage once the session ends; does not change agent behavior.
#     ctx.add_shutdown_callback(_log_usage)

#     # --- Start LiveKit AgentSession ---------------------------------------
#     await session.start(
#         room=ctx.room,
#         agent=Assistant(),
#         room_options=room_io.RoomOptions(
#             audio_input=room_io.AudioInputOptions(
#                 noise_cancellation=lambda params: (
#                     noise_cancellation.BVCTelephony()
#                     if params.participant.kind
#                     == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
#                     else noise_cancellation.BVC()
#                 ),
#             ),
#         ),
#     )

#     # Initial greeting from the agent (text only; TTS handled locally).
#     await session.generate_reply(
#         instructions=SESSION_INSTRUCTION,
#     )

# if __name__ == "__main__":
#     agents.cli.run_app(server)












#-----------only stt is not working





# import logging
# from dotenv import load_dotenv

# from livekit import agents, rtc
# from livekit.agents import Agent, AgentServer, AgentSession, room_io
# from livekit.plugins import openai, noise_cancellation

# from tools import get_weather, search_web
# from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION

# # --------------------------------------------------
# # Setup
# # --------------------------------------------------
# load_dotenv()
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger("voice-agent")

# # --------------------------------------------------
# # Agent Definition
# # --------------------------------------------------
# class Assistant(Agent):
#     def __init__(self):
#         super().__init__(
#             instructions=AGENT_INSTRUCTION,
#             tools=[get_weather, search_web],
#         )

# # --------------------------------------------------
# # Agent Server
# # --------------------------------------------------
# server = AgentServer()

# @server.rtc_session()
# async def voice_agent(ctx: agents.JobContext):
#     logger.info("Starting voice agent session")

#     # LLM
#     llm = openai.LLM(
#         model="gpt-4o-mini",
#         temperature=0.3,
#     )

#     # STT
#     stt = openai.STT(
#         model="gpt-4o-transcribe",
#         language="en",
#     )

#     # TTS
#     tts = openai.TTS(
#         model="gpt-4o-mini-tts",
#         voice="alloy",
#     )

#     # ✅ VERSION-SAFE AgentSession
#     session = AgentSession(
#         llm=llm,
#         stt=stt,
#         tts=tts,
#     )

#     # Start session (THIS is where agent joins room)
#     await session.start(
#         room=ctx.room,
#         agent=Assistant(),
#         room_options=room_io.RoomOptions(
#             audio_input=room_io.AudioInputOptions(
#                 noise_cancellation=lambda params: (
#                     noise_cancellation.BVCTelephony()
#                     if params.participant.kind
#                     == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
#                     else noise_cancellation.BVC()
#                 )
#             )
#         ),
#     )

#     # Initial greeting
#     await session.generate_reply(
#         instructions=SESSION_INSTRUCTION
#     )

#     async def shutdown():
#         logger.info("Voice agent shutting down")

#     ctx.add_shutdown_callback(shutdown)

# # --------------------------------------------------
# # Run
# # --------------------------------------------------
# if __name__ == "__main__":
#     agents.cli.run_app(server)


























# import asyncio
# import threading
# import queue
# import time
# import os
# import json
# from dotenv import load_dotenv

# load_dotenv()

# # ------------------ TTS ------------------
# import pyttsx3
# _tts_engine = pyttsx3.init()
# _tts_queue = queue.Queue()
# _tts_lock = threading.Lock()

# def _tts_worker():
#     while True:
#         text = _tts_queue.get()
#         if text is None:
#             break
#         try:
#             _tts_engine.stop()
#             _tts_engine.say(text)
#             _tts_engine.runAndWait()
#         except Exception:
#             continue

# _tts_thread = threading.Thread(target=_tts_worker, daemon=True)
# _tts_thread.start()

# def speak_interruptible(text):
#     with _tts_lock:
#         while not _tts_queue.empty():
#             _tts_queue.get_nowait()
#         _tts_queue.put(text)

# # ------------------ STT ------------------
# whisper_model = None
# try:
#     import whisper
#     whisper_model = whisper.load_model("base")
# except Exception:
#     print("Whisper not available")

# vosk_rec = None
# try:
#     import vosk
#     vosk_path = "vosk-model-small-en-us-0.15"
#     if os.path.exists(vosk_path):
#         vosk_model = vosk.Model(vosk_path)
#         vosk_rec = vosk.KaldiRecognizer(vosk_model, 16000)
#     else:
#         print("VOSK model path invalid, skipping")
# except Exception:
#     print("VOSK not available")

# # ------------------ LiveKit ------------------
# from livekit import agents
# from livekit.agents import AgentServer, Agent

# # ------------------ LLM ------------------
# from livekit.plugins import openai

# server = AgentServer()

# class Assistant(Agent):
#     def __init__(self):
#         super().__init__(instructions="You are a helpful AI assistant.", tools=[])

# # ------------------ Voice Agent ------------------
# @server.rtc_session()
# async def voice_agent(ctx: agents.JobContext):
#     try:
#         assistant = Assistant()

#         # Initialize GPT-4o mini Realtime model
#         llm = None
#         try:
#             llm = openai.realtime.RealtimeModel(model="gpt-4o-mini-realtime-preview")
#         except Exception as e:
#             print("LLM not available:", e)

#         session = ctx.create_session(agent=assistant, llm=llm)

#         # Start the session and join the room
#         await session.start(room=ctx.room)
#         print(f"Agent joined room: {ctx.room.name}")

#         # ------------------ Audio Handling ------------------
#         async def handle_audio(track):
#             buffer = []
#             last_time = time.time()
#             async for frame in track.recv():
#                 pcm = frame.to_bytes()  # Latest SDK method
#                 buffer.append(pcm)
#                 last_time = time.time()

#                 # Simple VAD: if silence for 1s, process buffer
#                 if time.time() - last_time > 1.0 and buffer:
#                     audio_data = b"".join(buffer)
#                     buffer = []
#                     text = ""

#                     # Whisper transcription
#                     if whisper_model:
#                         try:
#                             result = whisper_model.transcribe(audio_data, fp16=False)
#                             text = result.get("text", "")
#                         except Exception:
#                             pass

#                     # VOSK fallback
#                     if not text and vosk_rec:
#                         try:
#                             vosk_rec.AcceptWaveform(audio_data)
#                             text = json.loads(vosk_rec.Result()).get("text", "")
#                         except Exception:
#                             pass

#                     if text:
#                         print("User said:", text)
#                         if llm:
#                             try:
#                                 reply = llm.generate(text)
#                                 speak_interruptible(reply)
#                             except Exception as e:
#                                 print("LLM failed:", e)

#         # Attach audio tracks
#         ctx.room.on("track_subscribed")(lambda track, _: asyncio.create_task(handle_audio(track)))

#         # Keep running until job is finished
#         await asyncio.Event().wait()  # Keeps the agent alive

#     except Exception as e:
#         print("Voice agent error:", e)

# # ------------------ Start Server ------------------
# if __name__ == "__main__":
#     print("Starting agent server...")
#     server.run()














#-----*3/2/2026






















# from dotenv import load_dotenv
# import asyncio
# import json
# import logging
# import os
# from typing import List

# from livekit import agents, rtc
# from livekit.agents import AgentServer, AgentSession, Agent, room_io
# from livekit.agents import llm as lk_llm
# from livekit.plugins import assemblyai, openai, noise_cancellation

# import pyttsx3

# from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
# from tools import get_weather, search_web


# load_dotenv(".env")
# logger = logging.getLogger(__name__)


# # -----------------------------
# # Conversation Cache
# # -----------------------------
# class ConversationCache:
#     """
#     Keeps a rolling text window of the conversation so that
#     GPT‑4o Mini always sees the full (truncated) context.
#     """

#     def __init__(self, max_chars: int = 6000):
#         self.buffer: List[str] = []
#         self.max_chars = max_chars

#     def add(self, text: str) -> None:
#         text = (text or "").strip()
#         if not text:
#             return
#         self.buffer.append(text)
#         self._trim()

#     def context(self) -> str:
#         return " ".join(self.buffer)

#     def _trim(self) -> None:
#         joined = " ".join(self.buffer)
#         while len(joined) > self.max_chars and self.buffer:
#             self.buffer.pop(0)
#             joined = " ".join(self.buffer)


# # -----------------------------
# # Local TTS (pyttsx3 ONLY) – simple per-call engine
# # -----------------------------
# class LocalTTS:
#     """
#     Simple pyttsx3 wrapper.

#     To avoid the "run loop already started" issue, we create a fresh
#     pyttsx3 engine for each utterance and block inside that call.
#     The caller should run this in a thread/executor so it doesn't
#     block the event loop.
#     """

#     def __init__(self, rate: int = 175) -> None:
#         self.rate = rate

#     def speak(self, text: str) -> None:
#         if not text:
#             return

#         logger.debug("LocalTTS (ephemeral) speaking: %r", text)
#         try:
#             engine = pyttsx3.init()
#             engine.setProperty("rate", self.rate)
#             engine.say(text)
#             try:
#                 engine.runAndWait()
#             except RuntimeError as e:
#                 # On some Windows setups, pyttsx3/SAPI complains that the "run loop
#                 # is already started". There is no clean programmatic fix; just log
#                 # and skip audio so the rest of the agent keeps running.
#                 if "run loop already started" in str(e):
#                     logger.error("pyttsx3 run loop already started; skipping this utterance")
#                 else:
#                     raise
#             finally:
#                 try:
#                     engine.stop()
#                 except Exception:
#                     pass
#             logger.debug("LocalTTS (ephemeral) finished")
#         except Exception:
#             logger.exception("LocalTTS engine error while speaking")


# # -----------------------------
# # Agent (NO LiveKit TTS)
# # -----------------------------
# class Assistant(Agent):
#     def __init__(self) -> None:
#         super().__init__(
#             instructions=AGENT_INSTRUCTION,
#             tools=[get_weather, search_web],
#         )


# # -----------------------------
# # Server
# # -----------------------------
# server = AgentServer()


# @server.rtc_session()
# async def my_agent(ctx: agents.JobContext) -> None:
#     """
#     Pipeline:
#     Live voice (mic) → AssemblyAI STT → cache full text →
#     GPT‑4o Mini (OpenAI LLM) → Local TTS (pyttsx3).
#     """

#     logger.debug("my_agent session started for room %s", ctx.room.name)

#     cache = ConversationCache()
#     tts = LocalTTS()

#     # Our own GPT‑4o Mini client (decoupled from AgentSession to
#     # avoid triggering LiveKit's internal TTS pipeline).
#     llm_client = openai.LLM(model="gpt-4o-mini")
#     logger.debug("Initialized OpenAI LLM client with model %s", llm_client.model)

#     # ✅ Only STT inside AgentSession; NO LLM, NO TTS.
#     # This way AgentSession will not try to do its own LLM→TTS voice
#     # generation, which is what was hitting the `tts_node` assertion.
#     session = AgentSession(
#         stt=assemblyai.STT(),
#     )

#     # ---- STT FINAL CALLBACK (via AgentSession events) ----
#     # AgentSession emits "user_input_transcribed" with unified payload.
#     # We only react on final transcripts.
#     @session.on("user_input_transcribed")
#     def _on_user_input(ev) -> None:  # type: ignore[no-untyped-def]
#         """Debugger hook: called on every STT transcript event."""
#         text = ""
#         try:
#             is_final = getattr(ev, "is_final", False)
#             transcript = (getattr(ev, "transcript", "") or "").strip()
#             logger.debug(
#                 "STT event received | is_final=%s, transcript=%r", is_final, transcript
#             )
#             if is_final:
#                 text = transcript
#         except Exception:
#             logger.exception("Error while processing STT event")
#             text = ""

#         if not text:
#             logger.debug("Ignoring empty or non-final transcript event")
#             return

#         logger.debug("Queueing handling of final transcript: %r", text)
#         asyncio.create_task(_handle_final_transcript(text))

#     # ---- ASYNC GPT + TTS PIPELINE ----
#     async def _handle_final_transcript(text: str) -> None:
#         """
#         Debugger hook: full pipeline for a final STT transcript.

#         Steps:
#         1) Update rolling conversation cache
#         2) Build ChatContext for the LLM
#         3) Call OpenAI LLM (streaming)
#         4) Aggregate reply text
#         5) Add reply to cache
#         6) Speak reply via local TTS
#         """
#         logger.debug("Handling final transcript: %r", text)

#         try:
#             # 1) add latest user text to rolling cache
#             cache.add(text)
#             conversation_ctx = cache.context()
#             logger.debug("Updated conversation context: %r", conversation_ctx)

#             # 2) build ChatContext from cache using LiveKit's LLM utilities
#             #    System includes both persistent persona + session/task instructions.
#             chat_ctx = lk_llm.ChatContext(
#                 items=[
#                     lk_llm.ChatMessage(
#                         role="system",
#                         content=[AGENT_INSTRUCTION, SESSION_INSTRUCTION],
#                     ),
#                     lk_llm.ChatMessage(
#                         role="user",
#                         content=[conversation_ctx],
#                     ),
#                 ]
#             )
#             logger.debug(
#                 "Built ChatContext for LLM | num_items=%d", len(list(chat_ctx.items))
#             )

#             # 3) call LLM with tool support and execute tool calls if emitted.
#             async def _run_llm_with_tools() -> str:
#                 tools = [get_weather, search_web]
#                 tool_map = {t.info.name: t for t in tools}
#                 tool_names = list(tool_map.keys())

#                 for attempt in range(3):
#                     logger.debug(
#                         "Calling LLM.chat (model=%s) attempt=%d with tools=%s ...",
#                         llm_client.model,
#                         attempt + 1,
#                         tool_names,
#                     )

#                     stream = llm_client.chat(chat_ctx=chat_ctx, tools=tools)

#                     reply_parts: list[str] = []
#                     tool_calls: dict[str, lk_llm.FunctionToolCall] = {}

#                     async with stream:
#                         async for chunk in stream:
#                             if chunk.delta and chunk.delta.content:
#                                 logger.debug("LLM token: %r", chunk.delta.content)
#                                 reply_parts.append(chunk.delta.content)

#                             if chunk.delta and chunk.delta.tool_calls:
#                                 for tc in chunk.delta.tool_calls:
#                                     # Keep the latest arguments for each call_id (streamed args can update)
#                                     tool_calls[tc.call_id] = tc
#                                     logger.debug(
#                                         "LLM tool_call: name=%s call_id=%s arguments=%r",
#                                         tc.name,
#                                         tc.call_id,
#                                         tc.arguments,
#                                     )

#                     reply = "".join(reply_parts).strip()
#                     if reply:
#                         return reply

#                     if not tool_calls:
#                         # No text and no tools -> nothing we can do
#                         return ""

#                     # Execute tool calls and append outputs to chat context,
#                     # then loop and ask the LLM again to produce a final answer.
#                     for call_id, tc in tool_calls.items():
#                         fn = tool_map.get(tc.name)
#                         if fn is None:
#                             out = f"Unknown tool: {tc.name}"
#                             is_error = True
#                         else:
#                             try:
#                                 args = json.loads(tc.arguments or "{}")
#                                 if not isinstance(args, dict):
#                                     raise ValueError("tool arguments must be a JSON object")
#                                 result = await fn(**args)  # type: ignore[misc]
#                                 out = str(result)
#                                 is_error = False
#                             except Exception as e:
#                                 out = f"Tool execution failed: {e}"
#                                 is_error = True

#                         chat_ctx.items.append(
#                             lk_llm.FunctionCall(
#                                 call_id=call_id,
#                                 name=tc.name,
#                                 arguments=tc.arguments or "{}",
#                             )
#                         )
#                         chat_ctx.items.append(
#                             lk_llm.FunctionCallOutput(
#                                 call_id=call_id,
#                                 name=tc.name,
#                                 output=out,
#                                 is_error=is_error,
#                             )
#                         )
#                         logger.debug(
#                             "Tool result appended | name=%s call_id=%s is_error=%s output=%r",
#                             tc.name,
#                             call_id,
#                             is_error,
#                             out,
#                         )

#                 return ""

#             # 4) run LLM (+tools) and get final assistant reply text
#             reply = (await _run_llm_with_tools()).strip()
#             logger.debug("Full LLM reply: %r", reply)

#             if not reply:
#                 logger.warning("LLM returned an empty reply; skipping TTS")
#                 return

#             # 5) store assistant reply in cache too
#             cache.add(reply)
#             logger.debug("Assistant reply added to conversation cache")

#             # 6) speak reply with local pyttsx3 in a background thread
#             logger.debug("Submitting reply to LocalTTS.speak() in executor")
#             loop = asyncio.get_running_loop()
#             await loop.run_in_executor(None, tts.speak, reply)
#             logger.debug("LocalTTS.speak() completed")

#         except Exception:
#             logger.exception("Error while handling final transcript")

#     # ---- START SESSION ----
#     await session.start(
#         room=ctx.room,
#         agent=Assistant(),
#         room_options=room_io.RoomOptions(
#             audio_input=room_io.AudioInputOptions(
#                 noise_cancellation=lambda params: (
#                     noise_cancellation.BVCTelephony()
#                     if params.participant.kind
#                     == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
#                     else noise_cancellation.BVC()
#                 )
#             )
#         ),
#     )

#     # ❌ Do NOT call session.generate_reply()
#     # That path may use the built-in TTS graph; we only want
#     # our custom GPT‑4o Mini → pyttsx3 path.


# if __name__ == "__main__":
#     agents.cli.run_app(server)


#------5/2/26




























# from dotenv import load_dotenv
# import asyncio
# import json
# import logging
# from typing import List, Optional

# from livekit import agents, rtc
# from livekit.agents import AgentServer, AgentSession, Agent, room_io
# from livekit.agents import llm as lk_llm
# from livekit.plugins import deepgram, openai, noise_cancellation

# import pyttsx3

# from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
# from tools import get_weather, search_web


# load_dotenv(".env")
# logger = logging.getLogger(__name__)


# # -----------------------------
# # Conversation Cache
# # -----------------------------
# class ConversationCache:
#     """
#     Rolling conversation buffer.
#     Preserves full context across barge-in / interruptions.
#     """

#     def __init__(self, max_chars: int = 6000):
#         self.buffer: List[str] = []
#         self.max_chars = max_chars

#     def add(self, text: str) -> None:
#         text = (text or "").strip()
#         if not text:
#             return
#         self.buffer.append(text)
#         self._trim()

#     def context(self) -> str:
#         return " ".join(self.buffer)

#     def _trim(self) -> None:
#         joined = " ".join(self.buffer)
#         while len(joined) > self.max_chars and self.buffer:
#             self.buffer.pop(0)
#             joined = " ".join(self.buffer)


# # -----------------------------
# # Local TTS (pyttsx3)
# # -----------------------------
# class LocalTTS:
#     """
#     Local interruptible TTS.
#     Runs in executor so it never blocks STT or LLM.
#     """

#     def __init__(self, rate: int = 175):
#         self.rate = rate

#     def speak(self, text: str) -> None:
#         if not text:
#             return

#         try:
#             engine = pyttsx3.init()
#             engine.setProperty("rate", self.rate)
#             engine.say(text)
#             engine.runAndWait()
#             engine.stop()
#         except Exception:
#             logger.exception("LocalTTS error")


# # -----------------------------
# # Agent (NO LiveKit LLM/TTS)
# # -----------------------------
# class Assistant(Agent):
#     def __init__(self):
#         super().__init__(
#             instructions=AGENT_INSTRUCTION,
#             tools=[get_weather, search_web],
#         )


# # -----------------------------
# # Server
# # -----------------------------
# server = AgentServer()


# @server.rtc_session()
# async def my_agent(ctx: agents.JobContext) -> None:
#     """
#     Pipeline:
#     Live Voice →
#     Deepgram Realtime STT →
#     Rolling Cache →
#     GPT-4o Mini (streaming) →
#     Local TTS (pyttsx3)

#     Barge-in is achieved because realtime STT continuously emits
#     partial/final transcripts that act as an interrupt signal,
#     allowing immediate cancellation of GPT streaming and TTS,
#     while preserving context via the rolling cache.
#     """

#     logger.info("Session started for room %s", ctx.room.name)

#     cache = ConversationCache()
#     tts = LocalTTS()

#     llm_client = openai.LLM(model="gpt-4o-mini")

#     # Track active LLM task for barge-in
#     current_llm_task: Optional[asyncio.Task] = None

#     # ✅ Deepgram realtime STT
#     session = AgentSession(
#         stt=deepgram.STTv2(
#             model="flux-general-en",
#             eager_eot_threshold=0.4,  # Faster end-of-utterance
#         )
#     )

#     # -----------------------------
#     # STT EVENT (BARGE-IN TRIGGER)
#     # -----------------------------
#     @session.on("user_input_transcribed")
#     def _on_user_input(ev) -> None:  # type: ignore
#         nonlocal current_llm_task

#         transcript = (getattr(ev, "transcript", "") or "").strip()
#         is_final = getattr(ev, "is_final", False)

#         if transcript:
#             # 🔴 BARGE-IN: cancel ongoing LLM/TTS immediately
#             if current_llm_task and not current_llm_task.done():
#                 logger.debug("Barge-in detected → cancelling LLM/TTS")
#                 current_llm_task.cancel()

#         if is_final and transcript:
#             asyncio.create_task(_handle_final_transcript(transcript))

#     # -----------------------------
#     # GPT + TTS PIPELINE
#     # -----------------------------
#     async def _handle_final_transcript(text: str) -> None:
#         nonlocal current_llm_task
#         current_llm_task = asyncio.current_task()

#         try:
#             # 1) Update cache
#             cache.add(text)
#             conversation_ctx = cache.context()

#             # 2) Build ChatContext
#             chat_ctx = lk_llm.ChatContext(
#                 items=[
#                     lk_llm.ChatMessage(
#                         role="system",
#                         content=[AGENT_INSTRUCTION, SESSION_INSTRUCTION],
#                     ),
#                     lk_llm.ChatMessage(
#                         role="user",
#                         content=[conversation_ctx],
#                     ),
#                 ]
#             )

#             # 3) Run GPT-4o Mini (streaming)
#             tools = [get_weather, search_web]
#             tool_map = {t.info.name: t for t in tools}

#             stream = llm_client.chat(chat_ctx=chat_ctx, tools=tools)
#             reply_parts: List[str] = []
#             tool_calls = {}

#             async with stream:
#                 async for chunk in stream:
#                     if chunk.delta and chunk.delta.content:
#                         reply_parts.append(chunk.delta.content)

#                     if chunk.delta and chunk.delta.tool_calls:
#                         for tc in chunk.delta.tool_calls:
#                             tool_calls[tc.call_id] = tc

#             reply = "".join(reply_parts).strip()
#             if not reply:
#                 return

#             # 4) Cache assistant reply
#             cache.add(reply)

#             # 5) Speak (interruptible)
#             loop = asyncio.get_running_loop()
#             await loop.run_in_executor(None, tts.speak, reply)

#         except asyncio.CancelledError:
#             logger.debug("LLM/TTS cancelled due to barge-in")
#         except Exception:
#             logger.exception("Error in transcript handler")

#     # -----------------------------
#     # START SESSION
#     # -----------------------------
#     await session.start(
#         room=ctx.room,
#         agent=Assistant(),
#         room_options=room_io.RoomOptions(
#             audio_input=room_io.AudioInputOptions(
#                 noise_cancellation=lambda params: (
#                     noise_cancellation.BVCTelephony()
#                     if params.participant.kind
#                     == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
#                     else noise_cancellation.BVC()
#                 )
#             )
#         ),
#     )


# if __name__ == "__main__":
#     agents.cli.run_app(server)




































#--------------working but doesnot handle the interruption


# from dotenv import load_dotenv
# import asyncio
# import json
# import logging
# from typing import List, Tuple

# from livekit import agents, rtc
# from livekit.agents import AgentServer, AgentSession, Agent, room_io
# from livekit.agents import llm as lk_llm
# from livekit.plugins import assemblyai, openai, noise_cancellation

# import pyttsx3

# from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
# from tools import get_weather, search_web

# load_dotenv(".env")
# logger = logging.getLogger(__name__)
# logging.basicConfig(level=logging.DEBUG)

# # ============================================================
# # Conversation Memory (ROLE AWARE)
# # ============================================================

# class ConversationMemory:
#     def __init__(self, max_turns: int = 10):
#         self.turns: List[Tuple[str, str]] = []  # (role, text)
#         self.max_turns = max_turns

#     def add(self, role: str, text: str):
#         text = text.strip()
#         if not text:
#             return
#         self.turns.append((role, text))
#         self.turns = self.turns[-self.max_turns :]

#     def to_chat_context(self) -> lk_llm.ChatContext:
#         items = [
#             lk_llm.ChatMessage(
#                 role="system",
#                 content=[AGENT_INSTRUCTION, SESSION_INSTRUCTION],
#             )
#         ]

#         for role, text in self.turns:
#             items.append(
#                 lk_llm.ChatMessage(
#                     role=role,
#                     content=[text],
#                 )
#             )

#         return lk_llm.ChatContext(items=items)

# # ============================================================
# # Local TTS (SAFE, BLOCKING, LOOP-PROOF)
# # ============================================================

# class LocalTTS:
#     def __init__(self, rate: int = 175):
#         self.rate = rate

#     def speak(self, text: str):
#         if not text:
#             return
#         engine = pyttsx3.init()
#         engine.setProperty("rate", self.rate)
#         engine.say(text)
#         engine.runAndWait()
#         engine.stop()

# # ============================================================
# # Agent (NO BUILT-IN LLM / TTS)
# # ============================================================

# class Assistant(Agent):
#     def __init__(self):
#         super().__init__(
#             instructions=AGENT_INSTRUCTION,
#             tools=[get_weather, search_web],
#         )

# # ============================================================
# # Server
# # ============================================================

# server = AgentServer()

# @server.rtc_session()
# async def my_agent(ctx: agents.JobContext):

#     logger.info("Agent started for room: %s", ctx.room.name)

#     memory = ConversationMemory()
#     tts = LocalTTS()
#     llm_client = openai.LLM(model="gpt-4o-mini")

#     # ---- LOOP PROTECTION FLAGS ----
#     is_speaking = False
#     last_assistant_reply = ""

#     session = AgentSession(
#         stt=assemblyai.STT(),
#     )

#     # ========================================================
#     # STT CALLBACK
#     # ========================================================

#     @session.on("user_input_transcribed")
#     def on_transcript(ev):
#         nonlocal is_speaking

#         transcript = (getattr(ev, "transcript", "") or "").strip()
#         is_final = getattr(ev, "is_final", False)

#         logger.debug("STT | final=%s | text=%r", is_final, transcript)

#         if not is_final:
#             return

#         # 🔒 GUARD 1: Ignore while speaking
#         if is_speaking:
#             logger.debug("Ignored transcript (agent speaking)")
#             return

#         # 🔒 GUARD 2: Ignore noise
#         if len(transcript) < 3:
#             logger.debug("Ignored transcript (too short)")
#             return

#         # 🔒 GUARD 3: Ignore echo
#         if transcript == last_assistant_reply:
#             logger.debug("Ignored transcript (echo)")
#             return

#         asyncio.create_task(handle_user_input(transcript))

#     # ========================================================
#     # LLM + TTS PIPELINE
#     # ========================================================

#     async def handle_user_input(user_text: str):
#         nonlocal is_speaking, last_assistant_reply

#         logger.info("User said: %s", user_text)

#         memory.add("user", user_text)
#         chat_ctx = memory.to_chat_context()

#         reply_text = await run_llm(chat_ctx)

#         if not reply_text:
#             return

#         memory.add("assistant", reply_text)
#         last_assistant_reply = reply_text

#         logger.info("Assistant reply: %s", reply_text)

#         # 🔒 LOCK SPEAKING
#         is_speaking = True
#         loop = asyncio.get_running_loop()
#         await loop.run_in_executor(None, tts.speak, reply_text)
#         is_speaking = False

#     # ========================================================
#     # LLM WITH TOOLS
#     # ========================================================

#     async def run_llm(chat_ctx: lk_llm.ChatContext) -> str:
#         tools = [get_weather, search_web]
#         tool_map = {t.info.name: t for t in tools}

#         stream = llm_client.chat(chat_ctx=chat_ctx, tools=tools)

#         reply_parts = []
#         tool_calls = {}

#         async with stream:
#             async for chunk in stream:
#                 if chunk.delta and chunk.delta.content:
#                     reply_parts.append(chunk.delta.content)

#                 if chunk.delta and chunk.delta.tool_calls:
#                     for tc in chunk.delta.tool_calls:
#                         tool_calls[tc.call_id] = tc

#         reply = "".join(reply_parts).strip()
#         if reply:
#             return reply

#         # ---- TOOL FALLBACK ----
#         for call_id, tc in tool_calls.items():
#             fn = tool_map.get(tc.name)
#             if not fn:
#                 continue

#             args = json.loads(tc.arguments or "{}")
#             result = await fn(**args)

#             chat_ctx.items.append(
#                 lk_llm.FunctionCall(
#                     call_id=call_id,
#                     name=tc.name,
#                     arguments=tc.arguments or "{}",
#                 )
#             )
#             chat_ctx.items.append(
#                 lk_llm.FunctionCallOutput(
#                     call_id=call_id,
#                     name=tc.name,
#                     output=str(result),
#                     is_error=False,
#                 )
#             )

#         # second pass
#         stream = llm_client.chat(chat_ctx=chat_ctx)
#         final_parts = []

#         async with stream:
#             async for chunk in stream:
#                 if chunk.delta and chunk.delta.content:
#                     final_parts.append(chunk.delta.content)

#         return "".join(final_parts).strip()

#     # ========================================================
#     # START SESSION
#     # ========================================================

#     await session.start(
#         room=ctx.room,
#         agent=Assistant(),
#         room_options=room_io.RoomOptions(
#             audio_input=room_io.AudioInputOptions(
#                 noise_cancellation=lambda params: (
#                     noise_cancellation.BVCTelephony()
#                     if params.participant.kind
#                     == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
#                     else noise_cancellation.BVC()
#                 )
#             )
#         ),
#     )

# if __name__ == "__main__":
#     agents.cli.run_app(server)


































# from dotenv import load_dotenv
# import asyncio
# import json
# import logging
# from typing import List

# from livekit import agents, rtc
# from livekit.agents import (
#     AgentServer,
#     AgentSession,
#     Agent,
#     room_io,
#     stt as lk_stt,
# )
# from livekit.agents import llm as lk_llm
# from livekit.plugins import openai, noise_cancellation, silero

# import pyttsx3

# from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
# from tools import get_weather, search_web


# # -------------------------------------------------------------------
# # ENV + LOGGING
# # -------------------------------------------------------------------
# load_dotenv(".env")

# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)


# # -------------------------------------------------------------------
# # Conversation Cache
# # -------------------------------------------------------------------
# class ConversationCache:
#     """
#     Keeps a rolling text window of the conversation so that
#     GPT-4o Mini always sees recent context.
#     """

#     def __init__(self, max_chars: int = 6000):
#         self.buffer: List[str] = []
#         self.max_chars = max_chars

#     def add(self, text: str) -> None:
#         text = (text or "").strip()
#         if not text:
#             return
#         self.buffer.append(text)
#         self._trim()

#     def context(self) -> str:
#         return " ".join(self.buffer)

#     def _trim(self) -> None:
#         joined = " ".join(self.buffer)
#         while len(joined) > self.max_chars and self.buffer:
#             self.buffer.pop(0)
#             joined = " ".join(self.buffer)


# # -------------------------------------------------------------------
# # Local TTS (pyttsx3)
# # -------------------------------------------------------------------
# class LocalTTS:
#     """
#     Simple pyttsx3 wrapper.
#     Creates a fresh engine per utterance to avoid Windows run-loop bugs.
#     """

#     def __init__(self, rate: int = 175) -> None:
#         self.rate = rate

#     def speak(self, text: str) -> None:
#         if not text:
#             logger.warning("LocalTTS: empty text, skipping")
#             return

#         logger.info("LocalTTS: Speaking text: %s", text[:50])
#         try:
#             engine = pyttsx3.init()
#             engine.setProperty("rate", self.rate)
#             engine.say(text)
#             engine.runAndWait()
#             engine.stop()
#             logger.info("LocalTTS: Finished speaking")
#         except Exception:
#             logger.exception("LocalTTS error")


# # -------------------------------------------------------------------
# # Agent Definition (NO LiveKit TTS)
# # -------------------------------------------------------------------
# class Assistant(Agent):
#     def __init__(self) -> None:
#         super().__init__(
#             instructions=AGENT_INSTRUCTION,
#             tools=[get_weather, search_web],
#         )


# # -------------------------------------------------------------------
# # Agent Server
# # -------------------------------------------------------------------
# server = AgentServer()


# @server.rtc_session()
# async def my_agent(ctx: agents.JobContext) -> None:
#     """
#     Pipeline:
#       Mic Audio
#         → WebRTC VAD
#         → OpenAI Realtime STT (gpt-realtime-mini)
#         → GPT-4o Mini
#         → Local TTS (pyttsx3)
#     """

#     logger.info("Session started for room %s", ctx.room.name)

#     cache = ConversationCache()
#     tts = LocalTTS()

#     # Standalone OpenAI LLM client
#     llm_client = openai.LLM(model="gpt-4o-mini")

#     # -------------------------------------------------------------------
#     # AgentSession (STT with StreamAdapter + Silero VAD)
#     # -------------------------------------------------------------------
#     session = AgentSession(
#         stt=lk_stt.StreamAdapter(
#             stt=openai.STT(model="gpt-4o-transcribe"),
#             vad=silero.VAD.load(),
#         ),
#     )

#     # -------------------------------------------------------------------
#     # STT FINAL CALLBACK
#     # -------------------------------------------------------------------
#     @session.on("user_input_transcribed")
#     def on_user_input(ev) -> None:
#         try:
#             # Log all STT events for debugging
#             logger.info("STT event: is_final=%s, transcript=%r", 
#                         getattr(ev, 'is_final', None), 
#                         getattr(ev, 'transcript', None))
            
#             if not getattr(ev, 'is_final', False):
#                 return

#             text = (getattr(ev, 'transcript', '') or "").strip()
#             if not text:
#                 logger.warning("STT: Final event but empty transcript")
#                 return

#             logger.info("User said: %s", text)
#             asyncio.create_task(handle_final_transcript(text))

#         except Exception:
#             logger.exception("STT callback error")

#     # -------------------------------------------------------------------
#     # LLM + TOOLS + LOCAL TTS
#     # -------------------------------------------------------------------
#     async def handle_final_transcript(text: str) -> None:
#         try:
#             # 1) Update cache
#             cache.add(text)

#             chat_ctx = lk_llm.ChatContext(
#                 items=[
#                     lk_llm.ChatMessage(
#                         role="system",
#                         content=[AGENT_INSTRUCTION, SESSION_INSTRUCTION],
#                     ),
#                     lk_llm.ChatMessage(
#                         role="user",
#                         content=[cache.context()],
#                     ),
#                 ]
#             )

#             tools = [get_weather, search_web]
#             tool_map = {t.info.name: t for t in tools}

#             stream = llm_client.chat(chat_ctx=chat_ctx, tools=tools)

#             reply_parts: list[str] = []
#             tool_calls: dict[str, lk_llm.FunctionToolCall] = {}

#             async with stream:
#                 async for chunk in stream:
#                     if chunk.delta and chunk.delta.content:
#                         reply_parts.append(chunk.delta.content)

#                     if chunk.delta and chunk.delta.tool_calls:
#                         for tc in chunk.delta.tool_calls:
#                             tool_calls[tc.call_id] = tc

#             reply = "".join(reply_parts).strip()

#             # Handle tool calls if any
#             for call_id, tc in tool_calls.items():
#                 fn = tool_map.get(tc.name)
#                 try:
#                     args = json.loads(tc.arguments or "{}")
#                     result = await fn(**args) if fn else "Unknown tool"
#                     is_error = False
#                 except Exception as e:
#                     result = f"Tool error: {e}"
#                     is_error = True

#                 chat_ctx.items.append(
#                     lk_llm.FunctionCall(
#                         call_id=call_id,
#                         name=tc.name,
#                         arguments=tc.arguments or "{}",
#                     )
#                 )
#                 chat_ctx.items.append(
#                     lk_llm.FunctionCallOutput(
#                         call_id=call_id,
#                         name=tc.name,
#                         output=str(result),
#                         is_error=is_error,
#                     )
#                 )

#             if not reply:
#                 logger.warning("LLM returned empty reply")
#                 return

#             logger.info("Assistant reply: %s", reply)
#             cache.add(reply)

#             logger.info("Starting TTS...")
#             loop = asyncio.get_running_loop()
#             await loop.run_in_executor(None, tts.speak, reply)
#             logger.info("TTS completed")

#         except Exception:
#             logger.exception("Transcript handling error")

#     # -------------------------------------------------------------------
#     # START SESSION
#     # -------------------------------------------------------------------
#     await session.start(
#         room=ctx.room,
#         agent=Assistant(),
#         room_options=room_io.RoomOptions(
#             audio_input=room_io.AudioInputOptions(
#                 noise_cancellation=lambda params: (
#                     noise_cancellation.BVCTelephony()
#                     if params.participant.kind
#                     == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
#                     else noise_cancellation.BVC()
#                 )
#             )
#         ),
#     )


# # -------------------------------------------------------------------
# # ENTRYPOINT
# # -------------------------------------------------------------------
# if __name__ == "__main__":
#     agents.cli.run_app(server)








#--------------9/2/2026 - LiveKit Realtime STT (Deepgram Nova-3)
# Replaced AssemblyAI STT with LiveKit Inference STT
# Architecture:
#   - Audio input via LiveKit room (mic)
#   - STT: LiveKit Inference (deepgram/nova-3) inside AgentSession
#   - LLM: OpenAI GPT-4o Mini (manual pipeline)
#   - TTS: Local pyttsx3 (NO LiveKit TTS)
#   - Tool calling via LiveKit LLM utilities
#   - Conversation memory via rolling text cache


























# import asyncio
# import json
# import logging
# from typing import List

# import pyttsx3
# from dotenv import load_dotenv

# from livekit import agents, rtc
# from livekit.agents import (
#     Agent,
#     AgentServer,
#     AgentSession,
#     inference,
#     room_io,
# )
# from livekit.agents import llm as lk_llm
# from livekit.plugins import noise_cancellation, openai, silero

# from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
# from tools import get_weather, search_web


# load_dotenv(".env")
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)


# # ---------------------------------------------------------------------------
# # Conversation Cache (rolling text window for GPT context)
# # ---------------------------------------------------------------------------
# class ConversationCache:
#     """Keeps a rolling text window so GPT-4o Mini always sees recent context."""

#     def __init__(self, max_chars: int = 6000):
#         self.buffer: List[str] = []
#         self.max_chars = max_chars

#     def add(self, text: str) -> None:
#         text = (text or "").strip()
#         if not text:
#             return
#         self.buffer.append(text)
#         self._trim()

#     def context(self) -> str:
#         return " ".join(self.buffer)

#     def _trim(self) -> None:
#         joined = " ".join(self.buffer)
#         while len(joined) > self.max_chars and self.buffer:
#             self.buffer.pop(0)
#             joined = " ".join(self.buffer)


# # ---------------------------------------------------------------------------
# # Local TTS (pyttsx3 ONLY) – per-call engine to avoid Windows run-loop issues
# # ---------------------------------------------------------------------------
# class LocalTTS:
#     """pyttsx3 wrapper. Creates fresh engine per utterance for Windows stability."""

#     def __init__(self, rate: int = 175) -> None:
#         self.rate = rate

#     def speak(self, text: str) -> None:
#         if not text:
#             return

#         logger.debug("LocalTTS speaking: %r", text[:50])
#         try:
#             engine = pyttsx3.init()
#             engine.setProperty("rate", self.rate)
#             engine.say(text)
#             try:
#                 engine.runAndWait()
#             except RuntimeError as e:
#                 if "run loop already started" in str(e):
#                     logger.error("pyttsx3 run loop conflict; skipping utterance")
#                 else:
#                     raise
#             finally:
#                 try:
#                     engine.stop()
#                 except Exception:
#                     pass
#             logger.debug("LocalTTS finished")
#         except Exception:
#             logger.exception("LocalTTS engine error")


# # ---------------------------------------------------------------------------
# # Agent Definition (NO LiveKit TTS)
# # ---------------------------------------------------------------------------
# class Assistant(Agent):
#     def __init__(self) -> None:
#         super().__init__(
#             instructions=AGENT_INSTRUCTION,
#             tools=[get_weather, search_web],
#         )


# # ---------------------------------------------------------------------------
# # Server
# # ---------------------------------------------------------------------------
# server = AgentServer()


# @server.rtc_session()
# async def my_agent(ctx: agents.JobContext) -> None:
#     """
#     Pipeline:
#       Live voice (mic) → LiveKit Realtime STT (Deepgram Nova-3) → 
#       Rolling cache → GPT-4o Mini (OpenAI LLM) → Local TTS (pyttsx3)

#     STT handled ONLY inside AgentSession.
#     All GPT → TTS logic handled manually (no session.generate_reply).
#     """

#     logger.info("Agent session started for room %s", ctx.room.name)

#     cache = ConversationCache()
#     tts = LocalTTS()

#     # Our own GPT-4o Mini client (decoupled from AgentSession to avoid
#     # triggering LiveKit's internal TTS pipeline)
#     llm_client = openai.LLM(model="gpt-4o-mini")
#     logger.debug("Initialized OpenAI LLM client: %s", llm_client.model)

    # -------------------------------------------------------------------------
    # STT ONLY inside AgentSession: Deepgram Nova-3 (native streaming)
    # NO LLM, NO TTS in session – prevents built-in voice pipeline
    # -------------------------------------------------------------------------
    # session = AgentSession(
    #     stt=deepgram.STT(
    #         model="nova-3",
    #         language="en",
    #         interim_results=True,
    #         punctuate=True,
    #         smart_format=True,
    #     ),
    #     vad=silero.VAD.load(),
    # )

#     # -------------------------------------------------------------------------
#     # STT FINAL CALLBACK (user_input_transcribed event)
#     # Only react on is_final=True transcripts
#     # -------------------------------------------------------------------------
#     @session.on("user_input_transcribed")
#     def _on_user_input(ev) -> None:
#         """Fired on every STT transcript event from LiveKit Realtime STT."""
#         text = ""
#         try:
#             is_final = getattr(ev, "is_final", False)
#             transcript = (getattr(ev, "transcript", "") or "").strip()
#             logger.debug(
#                 "STT event | is_final=%s, transcript=%r", is_final, transcript
#             )

#             # Only process final transcripts (ignore interim)
#             if is_final:
#                 text = transcript
#         except Exception:
#             logger.exception("Error processing STT event")
#             text = ""

#         if not text:
#             logger.debug("Ignoring empty or non-final transcript")
#             return

#         logger.info("User said: %s", text)
#         asyncio.create_task(_handle_final_transcript(text))

#     # -------------------------------------------------------------------------
#     # ASYNC GPT + TTS PIPELINE (manual, no session.generate_reply)
#     # -------------------------------------------------------------------------
#     async def _handle_final_transcript(text: str) -> None:
#         """
#         Full pipeline for a final STT transcript:
#         1) Update rolling conversation cache
#         2) Build ChatContext for the LLM
#         3) Call OpenAI LLM (streaming) with tool support
#         4) Execute tool calls if any
#         5) Aggregate reply text
#         6) Add reply to cache
#         7) Speak reply via local TTS
#         """
#         logger.debug("Handling final transcript: %r", text)

#         try:
#             # 1) Add user text to rolling cache
#             cache.add(f"User: {text}")
#             conversation_ctx = cache.context()
#             logger.debug("Conversation context length: %d chars", len(conversation_ctx))

#             # 2) Build ChatContext using LiveKit's LLM utilities
#             chat_ctx = lk_llm.ChatContext(
#                 items=[
#                     lk_llm.ChatMessage(
#                         role="system",
#                         content=[AGENT_INSTRUCTION, SESSION_INSTRUCTION],
#                     ),
#                     lk_llm.ChatMessage(
#                         role="user",
#                         content=[conversation_ctx],
#                     ),
#                 ]
#             )

#             # 3) Call LLM with tool support
#             async def _run_llm_with_tools() -> str:
#                 tools = [get_weather, search_web]
#                 tool_map = {t.info.name: t for t in tools}
#                 tool_names = list(tool_map.keys())

#                 for attempt in range(3):
#                     logger.debug(
#                         "LLM call attempt=%d with tools=%s", attempt + 1, tool_names
#                     )

#                     stream = llm_client.chat(chat_ctx=chat_ctx, tools=tools)

#                     reply_parts: list[str] = []
#                     tool_calls: dict[str, lk_llm.FunctionToolCall] = {}

#                     async with stream:
#                         async for chunk in stream:
#                             if chunk.delta and chunk.delta.content:
#                                 reply_parts.append(chunk.delta.content)

#                             if chunk.delta and chunk.delta.tool_calls:
#                                 for tc in chunk.delta.tool_calls:
#                                     tool_calls[tc.call_id] = tc
#                                     logger.debug(
#                                         "Tool call: name=%s args=%r",
#                                         tc.name,
#                                         tc.arguments,
#                                     )

#                     reply = "".join(reply_parts).strip()
#                     if reply:
#                         return reply

#                     if not tool_calls:
#                         return ""

#                     # 4) Execute tool calls and append to context
#                     for call_id, tc in tool_calls.items():
#                         fn = tool_map.get(tc.name)
#                         if fn is None:
#                             out = f"Unknown tool: {tc.name}"
#                             is_error = True
#                         else:
#                             try:
#                                 args = json.loads(tc.arguments or "{}")
#                                 if not isinstance(args, dict):
#                                     raise ValueError("Arguments must be JSON object")
#                                 result = await fn(**args)
#                                 out = str(result)
#                                 is_error = False
#                             except Exception as e:
#                                 out = f"Tool error: {e}"
#                                 is_error = True

#                         chat_ctx.items.append(
#                             lk_llm.FunctionCall(
#                                 call_id=call_id,
#                                 name=tc.name,
#                                 arguments=tc.arguments or "{}",
#                             )
#                         )
#                         chat_ctx.items.append(
#                             lk_llm.FunctionCallOutput(
#                                 call_id=call_id,
#                                 name=tc.name,
#                                 output=out,
#                                 is_error=is_error,
#                             )
#                         )
#                         logger.debug(
#                             "Tool result: name=%s is_error=%s output=%r",
#                             tc.name,
#                             is_error,
#                             out[:100],
#                         )

#                 return ""

#             # 5) Get final assistant reply
#             reply = (await _run_llm_with_tools()).strip()
#             logger.debug("LLM reply: %r", reply[:100] if reply else "(empty)")

#             if not reply:
#                 logger.warning("LLM returned empty reply; skipping TTS")
#                 return

#             # 6) Store assistant reply in cache
#             cache.add(f"Assistant: {reply}")
#             logger.info("Assistant: %s", reply)

#             # 7) Speak reply with local pyttsx3 in background thread
#             logger.debug("Starting LocalTTS...")
#             loop = asyncio.get_running_loop()
#             await loop.run_in_executor(None, tts.speak, reply)
#             logger.debug("LocalTTS completed")

#         except Exception:
#             logger.exception("Error handling final transcript")

#     # -------------------------------------------------------------------------
#     # START SESSION
#     # -------------------------------------------------------------------------
#     await session.start(
#         room=ctx.room,
#         agent=Assistant(),
#         room_options=room_io.RoomOptions(
#             audio_input=room_io.AudioInputOptions(
#                 noise_cancellation=lambda params: (
#                     noise_cancellation.BVCTelephony()
#                     if params.participant.kind
#                     == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
#                     else noise_cancellation.BVC()
#                 )
#             )
#         ),
#     )

#     logger.info("Agent session running. Listening for user speech...")

#     # NO session.generate_reply() – all GPT→TTS handled manually via
#     # user_input_transcribed event callback


# if __name__ == "__main__":
#     agents.cli.run_app(server)





























#-----assemblyai stt
# from dotenv import load_dotenv
# import asyncio
# import json
# import logging
# import os
# from typing import List

# from livekit import agents, rtc
# from livekit.agents import AgentServer, AgentSession, Agent, room_io
# from livekit.agents import llm as lk_llm
# from livekit.plugins import assemblyai, openai, noise_cancellation

# import pyttsx3

# from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
# from tools import get_weather, search_web


# load_dotenv(".env")
# logger = logging.getLogger(__name__)


# # -----------------------------
# # Conversation Cache
# # -----------------------------
# class ConversationCache:
#     """
#     Keeps a rolling text window of the conversation so that
#     GPT‑4o Mini always sees the full (truncated) context.
#     """

#     def __init__(self, max_chars: int = 6000):
#         self.buffer: List[str] = []
#         self.max_chars = max_chars

#     def add(self, text: str) -> None:
#         text = (text or "").strip()
#         if not text:
#             return
#         self.buffer.append(text)
#         self._trim()

#     def context(self) -> str:
#         return " ".join(self.buffer)

#     def _trim(self) -> None:
#         joined = " ".join(self.buffer)
#         while len(joined) > self.max_chars and self.buffer:
#             self.buffer.pop(0)
#             joined = " ".join(self.buffer)


# # -----------------------------
# # Local TTS (pyttsx3 ONLY) – simple per-call engine
# # -----------------------------
# class LocalTTS:
#     """
#     Simple pyttsx3 wrapper.

#     To avoid the "run loop already started" issue, we create a fresh
#     pyttsx3 engine for each utterance and block inside that call.
#     The caller should run this in a thread/executor so it doesn't
#     block the event loop.
#     """

#     def __init__(self, rate: int = 175) -> None:
#         self.rate = rate

#     def speak(self, text: str) -> None:
#         if not text:
#             return

#         logger.debug("LocalTTS (ephemeral) speaking: %r", text)
#         try:
#             engine = pyttsx3.init()
#             engine.setProperty("rate", self.rate)
#             engine.say(text)
#             try:
#                 engine.runAndWait()
#             except RuntimeError as e:
#                 # On some Windows setups, pyttsx3/SAPI complains that the "run loop
#                 # is already started". There is no clean programmatic fix; just log
#                 # and skip audio so the rest of the agent keeps running.
#                 if "run loop already started" in str(e):
#                     logger.error("pyttsx3 run loop already started; skipping this utterance")
#                 else:
#                     raise
#             finally:
#                 try:
#                     engine.stop()
#                 except Exception:
#                     pass
#             logger.debug("LocalTTS (ephemeral) finished")
#         except Exception:
#             logger.exception("LocalTTS engine error while speaking")


# # -----------------------------
# # Agent (NO LiveKit TTS)
# # -----------------------------
# class Assistant(Agent):
#     def __init__(self) -> None:
#         super().__init__(
#             instructions=AGENT_INSTRUCTION,
#             tools=[get_weather, search_web],
#         )


# # -----------------------------
# # Server
# # -----------------------------
# server = AgentServer()


# @server.rtc_session()
# async def my_agent(ctx: agents.JobContext) -> None:
#     """
#     Pipeline:
#     Live voice (mic) → AssemblyAI STT → cache full text →
#     GPT‑4o Mini (OpenAI LLM) → Local TTS (pyttsx3).
#     """

#     logger.debug("my_agent session started for room %s", ctx.room.name)

#     cache = ConversationCache()
#     tts = LocalTTS()

#     # Our own GPT‑4o Mini client (decoupled from AgentSession to
#     # avoid triggering LiveKit's internal TTS pipeline).
#     llm_client = openai.LLM(model="gpt-4o-mini")
#     logger.debug("Initialized OpenAI LLM client with model %s", llm_client.model)

#     # ✅ Only STT inside AgentSession; NO LLM, NO TTS.
#     # This way AgentSession will not try to do its own LLM→TTS voice
#     # generation, which is what was hitting the `tts_node` assertion.
#     session = AgentSession(
#         stt=assemblyai.STT(),
#     )

#     # ---- STT FINAL CALLBACK (via AgentSession events) ----
#     # AgentSession emits "user_input_transcribed" with unified payload.
#     # We only react on final transcripts.
#     @session.on("user_input_transcribed")
#     def _on_user_input(ev) -> None:  # type: ignore[no-untyped-def]
#         """Debugger hook: called on every STT transcript event."""
#         text = ""
#         try:
#             is_final = getattr(ev, "is_final", False)
#             transcript = (getattr(ev, "transcript", "") or "").strip()
#             logger.debug(
#                 "STT event received | is_final=%s, transcript=%r", is_final, transcript
#             )
#             if is_final:
#                 text = transcript
#         except Exception:
#             logger.exception("Error while processing STT event")
#             text = ""

#         if not text:
#             logger.debug("Ignoring empty or non-final transcript event")
#             return

#         logger.debug("Queueing handling of final transcript: %r", text)
#         asyncio.create_task(_handle_final_transcript(text))

#     # ---- ASYNC GPT + TTS PIPELINE ----
#     async def _handle_final_transcript(text: str) -> None:
#         """
#         Debugger hook: full pipeline for a final STT transcript.

#         Steps:
#         1) Update rolling conversation cache
#         2) Build ChatContext for the LLM
#         3) Call OpenAI LLM (streaming)
#         4) Aggregate reply text
#         5) Add reply to cache
#         6) Speak reply via local TTS
#         """
#         logger.debug("Handling final transcript: %r", text)

#         try:
#             # 1) add latest user text to rolling cache
#             cache.add(text)
#             conversation_ctx = cache.context()
#             logger.debug("Updated conversation context: %r", conversation_ctx)

#             # 2) build ChatContext from cache using LiveKit's LLM utilities
#             #    System includes both persistent persona + session/task instructions.
#             chat_ctx = lk_llm.ChatContext(
#                 items=[
#                     lk_llm.ChatMessage(
#                         role="system",
#                         content=[AGENT_INSTRUCTION, SESSION_INSTRUCTION],
#                     ),
#                     lk_llm.ChatMessage(
#                         role="user",
#                         content=[conversation_ctx],
#                     ),
#                 ]
#             )
#             logger.debug(
#                 "Built ChatContext for LLM | num_items=%d", len(list(chat_ctx.items))
#             )

#             # 3) call LLM with tool support and execute tool calls if emitted.
#             async def _run_llm_with_tools() -> str:
#                 tools = [get_weather, search_web]
#                 tool_map = {t.info.name: t for t in tools}
#                 tool_names = list(tool_map.keys())

#                 for attempt in range(3):
#                     logger.debug(
#                         "Calling LLM.chat (model=%s) attempt=%d with tools=%s ...",
#                         llm_client.model,
#                         attempt + 1,
#                         tool_names,
#                     )

#                     stream = llm_client.chat(chat_ctx=chat_ctx, tools=tools)

#                     reply_parts: list[str] = []
#                     tool_calls: dict[str, lk_llm.FunctionToolCall] = {}

#                     async with stream:
#                         async for chunk in stream:
#                             if chunk.delta and chunk.delta.content:
#                                 logger.debug("LLM token: %r", chunk.delta.content)
#                                 reply_parts.append(chunk.delta.content)

#                             if chunk.delta and chunk.delta.tool_calls:
#                                 for tc in chunk.delta.tool_calls:
#                                     # Keep the latest arguments for each call_id (streamed args can update)
#                                     tool_calls[tc.call_id] = tc
#                                     logger.debug(
#                                         "LLM tool_call: name=%s call_id=%s arguments=%r",
#                                         tc.name,
#                                         tc.call_id,
#                                         tc.arguments,
#                                     )

#                     reply = "".join(reply_parts).strip()
#                     if reply:
#                         return reply

#                     if not tool_calls:
#                         # No text and no tools -> nothing we can do
#                         return ""

#                     # Execute tool calls and append outputs to chat context,
#                     # then loop and ask the LLM again to produce a final answer.
#                     for call_id, tc in tool_calls.items():
#                         fn = tool_map.get(tc.name)
#                         if fn is None:
#                             out = f"Unknown tool: {tc.name}"
#                             is_error = True
#                         else:
#                             try:
#                                 args = json.loads(tc.arguments or "{}")
#                                 if not isinstance(args, dict):
#                                     raise ValueError("tool arguments must be a JSON object")
#                                 result = await fn(**args)  # type: ignore[misc]
#                                 out = str(result)
#                                 is_error = False
#                             except Exception as e:
#                                 out = f"Tool execution failed: {e}"
#                                 is_error = True

#                         chat_ctx.items.append(
#                             lk_llm.FunctionCall(
#                                 call_id=call_id,
#                                 name=tc.name,
#                                 arguments=tc.arguments or "{}",
#                             )
#                         )
#                         chat_ctx.items.append(
#                             lk_llm.FunctionCallOutput(
#                                 call_id=call_id,
#                                 name=tc.name,
#                                 output=out,
#                                 is_error=is_error,
#                             )
#                         )
#                         logger.debug(
#                             "Tool result appended | name=%s call_id=%s is_error=%s output=%r",
#                             tc.name,
#                             call_id,
#                             is_error,
#                             out,
#                         )

#                 return ""

#             # 4) run LLM (+tools) and get final assistant reply text
#             reply = (await _run_llm_with_tools()).strip()
#             logger.debug("Full LLM reply: %r", reply)

#             if not reply:
#                 logger.warning("LLM returned an empty reply; skipping TTS")
#                 return

#             # 5) store assistant reply in cache too
#             cache.add(reply)
#             logger.debug("Assistant reply added to conversation cache")

#             # 6) speak reply with local pyttsx3 in a background thread
#             logger.debug("Submitting reply to LocalTTS.speak() in executor")
#             loop = asyncio.get_running_loop()
#             await loop.run_in_executor(None, tts.speak, reply)
#             logger.debug("LocalTTS.speak() completed")

#         except Exception:
#             logger.exception("Error while handling final transcript")

#     # ---- START SESSION ----
#     await session.start(
#         room=ctx.room,
#         agent=Assistant(),
#         room_options=room_io.RoomOptions(
#             audio_input=room_io.AudioInputOptions(
#                 noise_cancellation=lambda params: (
#                     noise_cancellation.BVCTelephony()
#                     if params.participant.kind
#                     == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
#                     else noise_cancellation.BVC()
#                 )
#             )
#         ),
#     )

#     # ❌ Do NOT call session.generate_reply()
#     # That path may use the built-in TTS graph; we only want
#     # our custom GPT‑4o Mini → pyttsx3 path.


# if __name__ == "__main__":
#     agents.cli.run_app(server)














#--------------9/2/2026 - Deepgram Nova-3 Streaming STT
# Architecture:
#   - Audio input via LiveKit room (mic)
#   - STT: Deepgram Nova-3 (native streaming) inside AgentSession
#   - LLM: OpenAI GPT-4o Mini (manual pipeline - NOT in AgentSession)
#   - TTS: Local pyttsx3 (NO LiveKit TTS)
#   - Tool calling via LiveKit LLM utilities
#   - Conversation memory via rolling text cache

# import asyncio
# import json
# import logging
# from typing import List

# import pyttsx3
# from dotenv import load_dotenv

# from livekit import agents, rtc
# from livekit.agents import (
#     Agent,
#     AgentServer,
#     AgentSession,
#     room_io,
# )
# from livekit.agents import llm as lk_llm
# from livekit.plugins import deepgram, noise_cancellation, openai, silero

# from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
# from tools import get_weather, search_web


# load_dotenv(".env")
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)


# # ---------------------------------------------------------------------------
# # Conversation Cache (rolling text window for GPT context)
# # ---------------------------------------------------------------------------
# class ConversationCache:
#     """Keeps a rolling text window so GPT-4o Mini always sees recent context."""

#     def __init__(self, max_chars: int = 6000):
#         self.buffer: List[str] = []
#         self.max_chars = max_chars

#     def add(self, text: str) -> None:
#         text = (text or "").strip()
#         if not text:
#             return
#         self.buffer.append(text)
#         self._trim()

#     def context(self) -> str:
#         return " ".join(self.buffer)

#     def _trim(self) -> None:
#         joined = " ".join(self.buffer)
#         while len(joined) > self.max_chars and self.buffer:
#             self.buffer.pop(0)
#             joined = " ".join(self.buffer)


# # ---------------------------------------------------------------------------
# # Local TTS (pyttsx3) - per-call engine to avoid Windows run-loop issues
# # ---------------------------------------------------------------------------
# class LocalTTS:
#     """pyttsx3 wrapper. Creates fresh engine per utterance for Windows stability."""

#     def __init__(self, rate: int = 175) -> None:
#         self.rate = rate

#     def speak(self, text: str) -> None:
#         if not text:
#             return

#         logger.debug("LocalTTS speaking: %r", text[:50])
#         try:
#             engine = pyttsx3.init()
#             engine.setProperty("rate", self.rate)
#             engine.say(text)
#             try:
#                 engine.runAndWait()
#             except RuntimeError as e:
#                 if "run loop already started" in str(e):
#                     logger.error("pyttsx3 run loop conflict; skipping utterance")
#                 else:
#                     raise
#             finally:
#                 try:
#                     engine.stop()
#                 except Exception:
#                     pass
#             logger.debug("LocalTTS finished")
#         except Exception:
#             logger.exception("LocalTTS engine error")


# # ---------------------------------------------------------------------------
# # Agent Definition (minimal - NO tools here, tools handled manually)
# # ---------------------------------------------------------------------------
# class Assistant(Agent):
#     def __init__(self) -> None:
#         super().__init__(
#             instructions=AGENT_INSTRUCTION,
#         )


# # ---------------------------------------------------------------------------
# # Server
# # ---------------------------------------------------------------------------
# server = AgentServer()


# @server.rtc_session()
# async def my_agent(ctx: agents.JobContext) -> None:
#     """
#     Pipeline:
#       Live voice (mic) -> Deepgram Nova-3 STT (streaming) ->
#       Rolling cache -> GPT-4o Mini (OpenAI LLM) -> Local TTS (pyttsx3)

#     STT handled ONLY inside AgentSession (with VAD).
#     LLM + TTS handled manually via user_input_transcribed event.
#     NO session.generate_reply() - prevents built-in TTS pipeline.
#     """

#     logger.info("Agent session started for room %s", ctx.room.name)

#     cache = ConversationCache()
#     tts = LocalTTS()

#     # Our own GPT-4o Mini client (decoupled from AgentSession to avoid
#     # triggering LiveKit's internal TTS pipeline)
#     llm_client = openai.LLM(model="gpt-4o-mini")
#     logger.debug("Initialized OpenAI LLM client: %s", llm_client.model)

#     # -------------------------------------------------------------------------
#     # STT ONLY inside AgentSession: Deepgram Nova-3 (native streaming)
#     # NO LLM, NO TTS in session - prevents built-in voice pipeline
#     # -------------------------------------------------------------------------
#     session = AgentSession(
#         stt=deepgram.STT(
#             model="nova-3",
#             language="en",
#             interim_results=True,
#             punctuate=True,
#             smart_format=True,
#         ),
#         vad=silero.VAD.load(),
#     )

#     # -------------------------------------------------------------------------
#     # STT FINAL CALLBACK (user_input_transcribed event)
#     # Only react on is_final=True transcripts
#     # -------------------------------------------------------------------------
#     @session.on("user_input_transcribed")
#     def _on_user_input(ev) -> None:
#         """Fired on every STT transcript event from Deepgram."""
#         text = ""
#         try:
#             is_final = getattr(ev, "is_final", False)
#             transcript = (getattr(ev, "transcript", "") or "").strip()
#             logger.debug(
#                 "STT event | is_final=%s, transcript=%r", is_final, transcript
#             )

#             # Only process final transcripts (ignore interim)
#             if is_final:
#                 text = transcript
#         except Exception:
#             logger.exception("Error processing STT event")
#             text = ""

#         if not text:
#             logger.debug("Ignoring empty or non-final transcript")
#             return

#         logger.info("User said: %s", text)
#         asyncio.create_task(_handle_final_transcript(text))

#     # -------------------------------------------------------------------------
#     # ASYNC GPT + TTS PIPELINE (manual, no session.generate_reply)
#     # -------------------------------------------------------------------------
#     async def _handle_final_transcript(text: str) -> None:
#         """
#         Full pipeline for a final STT transcript:
#         1) Update rolling conversation cache
#         2) Build ChatContext for the LLM
#         3) Call OpenAI LLM (streaming) with tool support
#         4) Execute tool calls if any
#         5) Aggregate reply text
#         6) Add reply to cache
#         7) Speak reply via local TTS
#         """
#         logger.debug("Handling final transcript: %r", text)

#         try:
#             # 1) Add user text to rolling cache
#             cache.add(f"User: {text}")
#             conversation_ctx = cache.context()
#             logger.debug("Conversation context length: %d chars", len(conversation_ctx))

#             # 2) Build ChatContext using LiveKit's LLM utilities
#             chat_ctx = lk_llm.ChatContext(
#                 items=[
#                     lk_llm.ChatMessage(
#                         role="system",
#                         content=[AGENT_INSTRUCTION, SESSION_INSTRUCTION],
#                     ),
#                     lk_llm.ChatMessage(
#                         role="user",
#                         content=[conversation_ctx],
#                     ),
#                 ]
#             )

#             # 3) Call LLM with tool support
#             async def _run_llm_with_tools() -> str:
#                 tools = [get_weather, search_web]
#                 tool_map = {t.info.name: t for t in tools}
#                 tool_names = list(tool_map.keys())

#                 for attempt in range(3):
#                     logger.debug(
#                         "LLM call attempt=%d with tools=%s", attempt + 1, tool_names
#                     )

#                     stream = llm_client.chat(chat_ctx=chat_ctx, tools=tools)

#                     reply_parts: list[str] = []
#                     tool_calls: dict[str, lk_llm.FunctionToolCall] = {}

#                     async with stream:
#                         async for chunk in stream:
#                             if chunk.delta and chunk.delta.content:
#                                 reply_parts.append(chunk.delta.content)

#                             if chunk.delta and chunk.delta.tool_calls:
#                                 for tc in chunk.delta.tool_calls:
#                                     tool_calls[tc.call_id] = tc
#                                     logger.debug(
#                                         "Tool call: name=%s args=%r",
#                                         tc.name,
#                                         tc.arguments,
#                                     )

#                     reply = "".join(reply_parts).strip()
#                     if reply:
#                         return reply

#                     if not tool_calls:
#                         return ""

#                     # 4) Execute tool calls and append to context
#                     for call_id, tc in tool_calls.items():
#                         fn = tool_map.get(tc.name)
#                         if fn is None:
#                             out = f"Unknown tool: {tc.name}"
#                             is_error = True
#                         else:
#                             try:
#                                 args = json.loads(tc.arguments or "{}")
#                                 if not isinstance(args, dict):
#                                     raise ValueError("Arguments must be JSON object")
#                                 result = await fn(**args)
#                                 out = str(result)
#                                 is_error = False
#                             except Exception as e:
#                                 out = f"Tool error: {e}"
#                                 is_error = True

#                         chat_ctx.items.append(
#                             lk_llm.FunctionCall(
#                                 call_id=call_id,
#                                 name=tc.name,
#                                 arguments=tc.arguments or "{}",
#                             )
#                         )
#                         chat_ctx.items.append(
#                             lk_llm.FunctionCallOutput(
#                                 call_id=call_id,
#                                 name=tc.name,
#                                 output=out,
#                                 is_error=is_error,
#                             )
#                         )
#                         logger.debug(
#                             "Tool result: name=%s is_error=%s output=%r",
#                             tc.name,
#                             is_error,
#                             out[:100],
#                         )

#                 return ""

#             # 5) Get final assistant reply
#             reply = (await _run_llm_with_tools()).strip()
#             logger.debug("LLM reply: %r", reply[:100] if reply else "(empty)")

#             if not reply:
#                 logger.warning("LLM returned empty reply; skipping TTS")
#                 return

#             # 6) Store assistant reply in cache
#             cache.add(f"Assistant: {reply}")
#             logger.info("Assistant: %s", reply)

#             # 7) Speak reply with local pyttsx3 in background thread
#             logger.debug("Starting LocalTTS...")
#             loop = asyncio.get_running_loop()
#             await loop.run_in_executor(None, tts.speak, reply)
#             logger.debug("LocalTTS completed")

#         except Exception:
#             logger.exception("Error handling final transcript")

#     # -------------------------------------------------------------------------
#     # START SESSION
#     # -------------------------------------------------------------------------
#     await session.start(
#         room=ctx.room,
#         agent=Assistant(),
#         room_options=room_io.RoomOptions(
#             audio_input=room_io.AudioInputOptions(
#                 noise_cancellation=lambda params: (
#                     noise_cancellation.BVCTelephony()
#                     if params.participant.kind
#                     == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
#                     else noise_cancellation.BVC()
#                 )
#             )
#         ),
#     )

#     logger.info("Agent session running. Listening for user speech...")

#     # NO session.generate_reply() - all GPT->TTS handled manually via
#     # user_input_transcribed event callback


# if __name__ == "__main__":
#     agents.cli.run_app(server)


# import asyncio
# import json
# import logging
# from typing import List
# import pyttsx3
# from dotenv import load_dotenv
# from livekit import agents, rtc
# from livekit.agents import (
#     Agent,
#     AgentServer,
#     AgentSession,
#     room_io,
# )
# from livekit.agents import llm as lk_llm
# from livekit.plugins import deepgram, noise_cancellation, openai, silero
# from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
# from tools import get_weather, search_web


# load_dotenv(".env")
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)


# # ---------------------------------------------------------------------------
# # Conversation Cache (rolling text window for GPT context)
# # ---------------------------------------------------------------------------
# class ConversationCache:
#     """Keeps a rolling text window so GPT-4o Mini always sees recent context."""

#     def __init__(self, max_chars: int = 6000):
#         self.buffer: List[str] = []
#         self.max_chars = max_chars

#     def add(self, text: str) -> None:
#         text = (text or "").strip()
#         if not text:
#             return
#         self.buffer.append(text)
#         self._trim()

#     def context(self) -> str:
#         return " ".join(self.buffer)

#     def _trim(self) -> None:
#         joined = " ".join(self.buffer)
#         while len(joined) > self.max_chars and self.buffer:
#             self.buffer.pop(0)
#             joined = " ".join(self.buffer)


# # ---------------------------------------------------------------------------
# # Local TTS (pyttsx3) - per-call engine to avoid Windows run-loop issues
# # ---------------------------------------------------------------------------
# class LocalTTS:
#     """pyttsx3 wrapper. Creates fresh engine per utterance for Windows stability."""

#     def __init__(self, rate: int = 175) -> None:
#         self.rate = rate

#     def speak(self, text: str) -> None:
#         if not text:
#             return

#         logger.debug("LocalTTS speaking: %r", text[:50])
#         try:
#             engine = pyttsx3.init()
#             engine.setProperty("rate", self.rate)
#             engine.say(text)
#             try:
#                 engine.runAndWait()
#             except RuntimeError as e:
#                 if "run loop already started" in str(e):
#                     logger.error("pyttsx3 run loop conflict; skipping utterance")
#                 else:
#                     raise
#             finally:
#                 try:
#                     engine.stop()
#                 except Exception:
#                     pass
#             logger.debug("LocalTTS finished")
#         except Exception:
#             logger.exception("LocalTTS engine error")


# # ---------------------------------------------------------------------------
# # Agent Definition (minimal - NO tools here, tools handled manually)
# # ---------------------------------------------------------------------------
# class Assistant(Agent):
#     def __init__(self) -> None:
#         super().__init__(
#             instructions=AGENT_INSTRUCTION,
#         )


# # ---------------------------------------------------------------------------
# # Server
# # ---------------------------------------------------------------------------
# server = AgentServer()


# @server.rtc_session()
# async def my_agent(ctx: agents.JobContext) -> None:
#     """
#     Pipeline:
#       Live voice (mic) -> Deepgram Nova-3 STT (streaming) ->
#       Rolling cache -> GPT-4o Mini (OpenAI LLM) -> Local TTS (pyttsx3)

#     STT handled ONLY inside AgentSession (with VAD).
#     LLM + TTS handled manually via user_input_transcribed event.
#     NO session.generate_reply() - prevents built-in TTS pipeline.
#     """

#     logger.info("Agent session started for room %s", ctx.room.name)

#     cache = ConversationCache()
#     tts = LocalTTS()

#     # Our own GPT-4o Mini client (decoupled from AgentSession to avoid
#     # triggering LiveKit's internal TTS pipeline)
#     llm_client = openai.LLM(model="gpt-4o-mini")
#     logger.debug("Initialized OpenAI LLM client: %s", llm_client.model)

#     # -------------------------------------------------------------------------
#     # STT ONLY inside AgentSession: Deepgram Nova-3 (native streaming)
#     # NO LLM, NO TTS in session - prevents built-in voice pipeline
#     # -------------------------------------------------------------------------
#     session = AgentSession(
#         stt=deepgram.STT(
#             model="nova-3",
#             language="en",
#             interim_results=True,
#             punctuate=True,
#             smart_format=True,
#         ),
#         vad=silero.VAD.load(),# voice activity detector
#     )

#     # -------------------------------------------------------------------------
#     # STT FINAL CALLBACK (user_input_transcribed event)
#     # Only react on is_final=True transcripts
#     # -------------------------------------------------------------------------
#     @session.on("user_input_transcribed")
#     def _on_user_input(ev) -> None:
#         """Fired on every STT transcript event from Deepgram."""
#         text = ""
#         try:
#             is_final = getattr(ev, "is_final", False)
#             transcript = (getattr(ev, "transcript", "") or "").strip()
#             logger.debug(
#                 "STT event | is_final=%s, transcript=%r", is_final, transcript
#             )

#             # Only process final transcripts (ignore interim)
#             if is_final:
#                 text = transcript
#         except Exception:
#             logger.exception("Error processing STT event")
#             text = ""

#         if not text:
#             logger.debug("Ignoring empty or non-final transcript")
#             return

#         logger.info("User said: %s", text)
#         asyncio.create_task(_handle_final_transcript(text))

#     # -------------------------------------------------------------------------
#     # ASYNC GPT + TTS PIPELINE (manual, no session.generate_reply)
#     # -------------------------------------------------------------------------
#     async def _handle_final_transcript(text: str) -> None:
#         """
#         Full pipeline for a final STT transcript:
#         1) Update rolling conversation cache
#         2) Build ChatContext for the LLM
#         3) Call OpenAI LLM (streaming) with tool support
#         4) Execute tool calls if any
#         5) Aggregate reply text
#         6) Add reply to cache
#         7) Speak reply via local TTS
#         """
#         logger.debug("Handling final transcript: %r", text)

#         try:
#             # 1) Add user text to rolling cache
#             cache.add(f"User: {text}")
#             conversation_ctx = cache.context()
#             logger.debug("Conversation context length: %d chars", len(conversation_ctx))

#             # 2) Build ChatContext using LiveKit's LLM utilities
#             chat_ctx = lk_llm.ChatContext(
#                 items=[
#                     lk_llm.ChatMessage(
#                         role="system",
#                         content=[AGENT_INSTRUCTION, SESSION_INSTRUCTION],
#                     ),
#                     lk_llm.ChatMessage(
#                         role="user",
#                         content=[conversation_ctx],
#                     ),
#                 ]
#             )

#             # 3) Call LLM with tool support
#             async def _run_llm_with_tools() -> str:
#                 tools = [get_weather, search_web]
#                 tool_map = {t.info.name: t for t in tools}
#                 tool_names = list(tool_map.keys())

#                 for attempt in range(3):
#                     logger.debug(
#                         "LLM call attempt=%d with tools=%s", attempt + 1, tool_names
#                     )

#                     stream = llm_client.chat(chat_ctx=chat_ctx, tools=tools)

#                     reply_parts: list[str] = []
#                     tool_calls: dict[str, lk_llm.FunctionToolCall] = {}

#                     async with stream:
#                         async for chunk in stream:
#                             if chunk.delta and chunk.delta.content:
#                                 reply_parts.append(chunk.delta.content)

#                             if chunk.delta and chunk.delta.tool_calls:
#                                 for tc in chunk.delta.tool_calls:
#                                     tool_calls[tc.call_id] = tc
#                                     logger.debug(
#                                         "Tool call: name=%s args=%r",
#                                         tc.name,
#                                         tc.arguments,
#                                     )

#                     reply = "".join(reply_parts).strip()
#                     if reply:
#                         return reply

#                     if not tool_calls:
#                         return ""

#                     # 4) Execute tool calls and append to context
#                     for call_id, tc in tool_calls.items():
#                         fn = tool_map.get(tc.name)
#                         if fn is None:
#                             out = f"Unknown tool: {tc.name}"
#                             is_error = True
#                         else:
#                             try:
#                                 args = json.loads(tc.arguments or "{}")
#                                 if not isinstance(args, dict):
#                                     raise ValueError("Arguments must be JSON object")
#                                 result = await fn(**args)
#                                 out = str(result)
#                                 is_error = False
#                             except Exception as e:
#                                 out = f"Tool error: {e}"
#                                 is_error = True

#                         chat_ctx.items.append(
#                             lk_llm.FunctionCall(
#                                 call_id=call_id,
#                                 name=tc.name,
#                                 arguments=tc.arguments or "{}",
#                             )
#                         )
#                         chat_ctx.items.append(
#                             lk_llm.FunctionCallOutput(
#                                 call_id=call_id,
#                                 name=tc.name,
#                                 output=out,
#                                 is_error=is_error,
#                             )
#                         )
#                         logger.debug(
#                             "Tool result: name=%s is_error=%s output=%r",
#                             tc.name,
#                             is_error,
#                             out[:100],
#                         )

#                 return ""

#             # 5) Get final assistant reply
#             reply = (await _run_llm_with_tools()).strip()
#             logger.debug("LLM reply: %r", reply[:100] if reply else "(empty)")

#             if not reply:
#                 logger.warning("LLM returned empty reply; skipping TTS")
#                 return

#             # 6) Store assistant reply in cache
#             cache.add(f"Assistant: {reply}")
#             logger.info("Assistant: %s", reply)

#             # 7) Speak reply with local pyttsx3 in background thread
#             logger.debug("Starting LocalTTS...")
#             loop = asyncio.get_running_loop()
#             await loop.run_in_executor(None, tts.speak, reply)
#             logger.debug("LocalTTS completed")

#         except Exception:
#             logger.exception("Error handling final transcript")

#     # -------------------------------------------------------------------------
#     # START SESSION
#     # -------------------------------------------------------------------------
#     await session.start(
#         room=ctx.room,
#         agent=Assistant(),
#         room_options=room_io.RoomOptions(
#             audio_input=room_io.AudioInputOptions(
#                 noise_cancellation=lambda params: (
#                     noise_cancellation.BVCTelephony()
#                     if params.participant.kind
#                     == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
#                     else noise_cancellation.BVC()
#                 )
#             )
#         ),
#     )

#     logger.info("Agent session running. Listening for user speech...")

#     # NO session.generate_reply() - all GPT->TTS handled manually via
#     # user_input_transcribed event callback


# if __name__ == "__main__":
#     agents.cli.run_app(server)





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
