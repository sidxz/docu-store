from enum import StrEnum


class ChatSurface(StrEnum):
    """Which chat surface a conversation belongs to.

    Distinct from the pipeline ``mode``, which is chosen per message and can
    change within a conversation. A conversation's surface is fixed at creation:
    it decides which sidebar the conversation appears in and which corpus its
    questions are answered from, and those are not things a follow-up should be
    able to switch.
    """

    RESEARCH = "research"
    LITERATURE = "literature"
