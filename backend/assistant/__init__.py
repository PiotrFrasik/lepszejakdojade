"""AI chat assistant (docs/api.md, "Assistant (#18)").

The model is reached through a ``ChatProvider`` (``assistant.providers``); Gemini is the
default implementation. The model can only call read-only tools (``assistant.tools``)
that wrap the existing timetable and journey services.

Privacy note: on the free tier of the Gemini API, Google may use prompts and responses
to improve its products. Do not send personal data to the assistant.
"""
