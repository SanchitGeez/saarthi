"""Offline conversation experiments; never imported by the application."""

# Configure before importing DeepEval. This CLI uses local artifacts, not cloud tracing.
import os

os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "1"
os.environ["CONFIDENT_TRACE_SAMPLE_RATE"] = "0"
os.environ["CONFIDENT_TRACE_FLUSH"] = "0"
os.environ["DEEPEVAL_DISABLE_DOTENV"] = "1"
