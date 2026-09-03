"""Model transports. One module per wire protocol.

Every provider exposes an async `chat_stream(messages, **opts) -> AsyncIterator[str]`
yielding raw text deltas. Sentence-splitting and prompt assembly live in core.py,
never here.
"""
