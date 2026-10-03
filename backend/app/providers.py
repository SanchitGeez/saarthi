"""Explicit provider selection. Keys never choose a provider or trigger hidden fallback."""
from app.config import settings


def missing_credentials(*, voice=True):
    required = [("OPENROUTER_API_KEY", settings.openrouter_api_key)] if settings.llm_provider == "openrouter" else [("GOOGLE_API_KEY", settings.google_api_key)]
    if voice:
        required += [("MURF_API_KEY (or MURF_AI)", settings.murf_api_key)] if settings.tts_provider == "murf" else [("ELEVEN_LABS_API_KEY", settings.eleven_labs_api_key)]
        required += [("DEEPGRAM_API_KEY", settings.deepgram_api_key)] if settings.stt_provider == "deepgram" else [("ELEVEN_LABS_API_KEY", settings.eleven_labs_api_key)]
    return list(dict.fromkeys(name for name, value in required if not value.strip()))


def build_llm():
    from livekit.agents import llm
    if settings.llm_provider == "openrouter":
        from livekit.plugins import openai
        return openai.LLM(api_key=settings.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1", model=settings.openrouter_model,
            max_completion_tokens=500, parallel_tool_calls=False, tool_choice="auto", temperature=0.2)
    from livekit.plugins import google
    models = [google.LLM(api_key=settings.google_api_key, model=settings.gemini_model,
        vertexai=False, max_output_tokens=500)]
    if settings.gemini_fallback_model and settings.gemini_fallback_model != settings.gemini_model:
        models.append(google.LLM(api_key=settings.google_api_key, model=settings.gemini_fallback_model,
            vertexai=False, max_output_tokens=500))
    return llm.FallbackAdapter(models, attempt_timeout=12, max_retry_per_llm=0)


def build_stt(language="auto"):
    from livekit.plugins import deepgram, elevenlabs
    if settings.stt_provider == "deepgram":
        return deepgram.STT(api_key=settings.deepgram_api_key, model=settings.deepgram_model,
            language=settings.deepgram_language, mip_opt_out=True)
    primary = "en" if language == "en" else "hi"
    secondary = ["hi"] if primary == "en" else ["en"]
    return elevenlabs.STT(api_key=settings.eleven_labs_api_key,
        model="scribe_v2_realtime", language_code=primary, secondary_languages=secondary,
        include_language_detection=False,
        server_vad={"vad_silence_threshold_secs": 0.8, "min_silence_duration_ms": 500},
        enable_logging=False)


def build_tts(*, streaming=True):
    from livekit.plugins import elevenlabs, murf
    if settings.tts_provider == "murf":
        return murf.TTS(api_key=settings.murf_api_key, model=settings.murf_model,
            voice=settings.murf_voice, locale=settings.murf_locale or None,
            style=settings.murf_style, streaming=streaming)
    return elevenlabs.TTS(api_key=settings.eleven_labs_api_key,
        voice_id=settings.eleven_labs_voice_id, model=settings.voice_tts_model, enable_logging=False)
