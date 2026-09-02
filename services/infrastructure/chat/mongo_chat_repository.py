"""MongoDB adapter for ChatRepository port."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import structlog
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument

from application.dtos.chat_dtos import (
    AgentTraceDTO,
    ChatFeedbackDTO,
    ChatFolderDTO,
    ChatMessageDTO,
    ContentBlockDTO,
    ConversationDTO,
    QueryContextDTO,
    SourceCitationDTO,
    TokenUsageDTO,
)
from domain.value_objects.chat_surface import ChatSurface

log = structlog.get_logger(__name__)

_CONVERSATIONS = "conversations"
_MESSAGES = "chat_messages"
_SUMMARIES = "conversation_summaries"
_FEEDBACK = "chat_feedback"
_FOLDERS = "chat_folders"


class MongoChatRepository:
    """ChatRepository adapter backed by MongoDB.

    Collections:
    - conversations: conversation metadata
    - chat_messages: individual messages with agent traces and citations
    - conversation_summaries: sliding-window summaries for context management
    """

    def __init__(
        self,
        client: AsyncIOMotorClient,
        db_name: str = "docu_store",
    ) -> None:
        self._db = client[db_name]
        self._conversations = self._db[_CONVERSATIONS]
        self._messages = self._db[_MESSAGES]
        self._summaries = self._db[_SUMMARIES]
        self._feedback = self._db[_FEEDBACK]
        self._folders = self._db[_FOLDERS]

    # --- Conversations ---

    async def create_conversation(
        self,
        conversation: ConversationDTO,
    ) -> ConversationDTO:
        doc = _conversation_to_doc(conversation)
        await self._conversations.insert_one(doc)
        log.debug(
            "chat.repo.conversation_created",
            conversation_id=str(conversation.conversation_id),
        )
        return conversation

    async def get_conversation(
        self,
        conversation_id: UUID,
        workspace_id: UUID | None = None,
        owner_id: UUID | None = None,
    ) -> ConversationDTO | None:
        query: dict = {"conversation_id": str(conversation_id)}
        if workspace_id:
            query["workspace_id"] = str(workspace_id)
        if owner_id:
            query["owner_id"] = str(owner_id)
        doc = await self._conversations.find_one(query)
        if doc is None:
            return None
        return _doc_to_conversation(doc)

    async def list_conversations(
        self,
        workspace_id: UUID,
        owner_id: UUID,
        skip: int = 0,
        limit: int = 20,
        is_archived: bool = False,
        folder_id: UUID | None = None,
        surface: ChatSurface = ChatSurface.RESEARCH,
    ) -> list[ConversationDTO]:
        query: dict = {
            "workspace_id": str(workspace_id),
            "owner_id": str(owner_id),
            "is_archived": is_archived,
            **_surface_query(surface),
        }
        if folder_id is not None:
            query["folder_id"] = str(folder_id)
        cursor = self._conversations.find(query).sort("updated_at", -1).skip(skip).limit(limit)
        return [_doc_to_conversation(doc) async for doc in cursor]

    async def list_recent_conversations(
        self,
        workspace_id: UUID,
        owner_id: UUID,
        limit: int,
    ) -> list[ConversationDTO]:
        query = {
            "workspace_id": str(workspace_id),
            "owner_id": str(owner_id),
            "is_archived": False,
            "message_count": {"$gt": 0},
            # The dashboard's recents link into /chat, so a literature
            # conversation listed here would open on the wrong surface.
            **_surface_query(ChatSurface.RESEARCH),
        }
        cursor = self._conversations.find(query).sort("updated_at", -1).limit(limit)
        return [_doc_to_conversation(doc) async for doc in cursor]

    async def delete_conversation(
        self,
        conversation_id: UUID,
        workspace_id: UUID | None = None,
        owner_id: UUID | None = None,
    ) -> bool:
        query: dict = {"conversation_id": str(conversation_id)}
        if workspace_id:
            query["workspace_id"] = str(workspace_id)
        if owner_id:
            query["owner_id"] = str(owner_id)
        result = await self._conversations.delete_one(query)
        if result.deleted_count > 0:
            # Also delete all messages and summaries
            cid = str(conversation_id)
            await self._messages.delete_many({"conversation_id": cid})
            await self._summaries.delete_many({"conversation_id": cid})
            log.debug("chat.repo.conversation_deleted", conversation_id=cid)
            return True
        return False

    async def update_conversation(
        self,
        conversation_id: UUID,
        *,
        title: str | None = None,
        message_count: int | None = None,
        model_used: str | None = None,
        is_archived: bool | None = None,
    ) -> bool:
        updates: dict = {"updated_at": datetime.now(UTC)}
        if title is not None:
            updates["title"] = title
        if message_count is not None:
            updates["message_count"] = message_count
        if model_used is not None:
            updates["model_used"] = model_used
        if is_archived is not None:
            updates["is_archived"] = is_archived

        result = await self._conversations.update_one(
            {"conversation_id": str(conversation_id)},
            {"$set": updates},
        )
        return result.modified_count > 0

    async def set_conversation_folder(
        self,
        conversation_id: UUID,
        folder_id: UUID | None,
        workspace_id: UUID,
        owner_id: UUID,
    ) -> bool:
        # No updated_at bump: filing must not reorder the recency-sorted list.
        result = await self._conversations.update_one(
            {
                "conversation_id": str(conversation_id),
                "workspace_id": str(workspace_id),
                "owner_id": str(owner_id),
            },
            {"$set": {"folder_id": str(folder_id) if folder_id else None}},
        )
        # matched, not modified: a concurrent identical move must not read as
        # "conversation not found" — matched=1/modified=0 is still success.
        return result.matched_count > 0

    # --- Folders ---

    async def create_folder(self, folder: ChatFolderDTO) -> ChatFolderDTO:
        await self._folders.insert_one(_folder_to_doc(folder))
        log.debug("chat.repo.folder_created", folder_id=str(folder.folder_id))
        return folder

    async def list_folders(
        self,
        workspace_id: UUID,
        owner_id: UUID,
    ) -> list[ChatFolderDTO]:
        cursor = self._folders.find(
            {"workspace_id": str(workspace_id), "owner_id": str(owner_id)},
        )
        folders = [_doc_to_folder(doc) async for doc in cursor]
        if not folders:
            return folders
        # Sort in Python: Mongo's default byte-wise sort puts "Z" before "a".
        folders.sort(key=lambda f: f.name.casefold())
        counts = await self._counts_by_folder(workspace_id, owner_id)
        for f in folders:
            f.chat_count = counts.get(str(f.folder_id), 0)
        return folders

    async def _counts_by_folder(
        self,
        workspace_id: UUID,
        owner_id: UUID,
    ) -> dict[str, int]:
        pipeline = [
            {
                "$match": {
                    "workspace_id": str(workspace_id),
                    "owner_id": str(owner_id),
                    "folder_id": {"$ne": None},
                    "is_archived": {"$ne": True},  # match the folder-view list filter
                },
            },
            {"$group": {"_id": "$folder_id", "n": {"$sum": 1}}},
        ]
        docs = await self._conversations.aggregate(pipeline).to_list(length=None)
        return {d["_id"]: int(d["n"]) for d in docs if d.get("_id")}

    async def get_folder(
        self,
        workspace_id: UUID,
        owner_id: UUID,
        folder_id: UUID,
    ) -> ChatFolderDTO | None:
        doc = await self._folders.find_one(
            {
                "folder_id": str(folder_id),
                "workspace_id": str(workspace_id),
                "owner_id": str(owner_id),
            },
        )
        return _doc_to_folder(doc) if doc else None

    async def rename_folder(
        self,
        workspace_id: UUID,
        owner_id: UUID,
        folder_id: UUID,
        name: str,
    ) -> ChatFolderDTO | None:
        # No updated_at bump — a rename is not a membership change.
        doc = await self._folders.find_one_and_update(
            {
                "folder_id": str(folder_id),
                "workspace_id": str(workspace_id),
                "owner_id": str(owner_id),
            },
            {"$set": {"name": name}},
            return_document=ReturnDocument.AFTER,
        )
        return _doc_to_folder(doc) if doc else None

    async def touch_folders(
        self,
        workspace_id: UUID,
        owner_id: UUID,
        folder_ids: list[UUID],
    ) -> None:
        if not folder_ids:
            return
        await self._folders.update_many(
            {
                "folder_id": {"$in": [str(f) for f in folder_ids]},
                "workspace_id": str(workspace_id),
                "owner_id": str(owner_id),
            },
            {"$set": {"updated_at": datetime.now(UTC)}},
        )

    async def delete_folder(
        self,
        workspace_id: UUID,
        owner_id: UUID,
        folder_id: UUID,
    ) -> bool:
        result = await self._folders.delete_one(
            {
                "folder_id": str(folder_id),
                "workspace_id": str(workspace_id),
                "owner_id": str(owner_id),
            },
        )
        return result.deleted_count > 0

    async def clear_folder(
        self,
        workspace_id: UUID,
        owner_id: UUID,
        folder_id: UUID,
    ) -> int:
        result = await self._conversations.update_many(
            {
                "folder_id": str(folder_id),
                "workspace_id": str(workspace_id),
                "owner_id": str(owner_id),
            },
            {"$set": {"folder_id": None}},
        )
        return result.modified_count

    # --- Messages ---

    async def append_message(
        self,
        message: ChatMessageDTO,
    ) -> ChatMessageDTO:
        doc = _message_to_doc(message)
        await self._messages.insert_one(doc)
        # Increment message count and update timestamp
        await self._conversations.update_one(
            {"conversation_id": str(message.conversation_id)},
            {
                "$inc": {"message_count": 1},
                "$set": {"updated_at": datetime.now(UTC)},
            },
        )
        return message

    async def get_messages(
        self,
        conversation_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ChatMessageDTO]:
        cursor = (
            self._messages.find({"conversation_id": str(conversation_id)})
            .sort("created_at", 1)
            .skip(skip)
            .limit(limit)
        )
        return [_doc_to_message(doc) async for doc in cursor]

    async def get_recent_messages(
        self,
        conversation_id: UUID,
        limit: int = 10,
    ) -> list[ChatMessageDTO]:
        cursor = (
            self._messages.find({"conversation_id": str(conversation_id)})
            .sort("created_at", -1)
            .limit(limit)
        )
        docs = [doc async for doc in cursor]
        docs.reverse()  # Return in chronological order
        return [_doc_to_message(doc) for doc in docs]

    # --- Conversation Summaries ---

    async def get_conversation_summary(
        self,
        conversation_id: UUID,
    ) -> str | None:
        doc = await self._summaries.find_one({"conversation_id": str(conversation_id)})
        if doc is None:
            return None
        return doc.get("summary")

    async def save_conversation_summary(
        self,
        conversation_id: UUID,
        summary: str,
    ) -> None:
        await self._summaries.update_one(
            {"conversation_id": str(conversation_id)},
            {
                "$set": {
                    "summary": summary,
                    "updated_at": datetime.now(UTC),
                },
                "$setOnInsert": {
                    "conversation_id": str(conversation_id),
                },
            },
            upsert=True,
        )

    # --- Feedback ---

    async def record_feedback(
        self,
        feedback: ChatFeedbackDTO,
    ) -> None:
        doc = {
            "conversation_id": str(feedback.conversation_id),
            "message_id": str(feedback.message_id),
            "workspace_id": str(feedback.workspace_id),
            "user_id": str(feedback.user_id),
            "feedback": feedback.feedback,
            "created_at": feedback.created_at,
        }
        await self._feedback.update_one(
            {
                "conversation_id": doc["conversation_id"],
                "message_id": doc["message_id"],
                "user_id": doc["user_id"],
            },
            {"$set": doc},
            upsert=True,
        )
        log.info(
            "chat.feedback.recorded",
            message_id=doc["message_id"],
            feedback=feedback.feedback,
        )

    async def get_feedback(
        self,
        conversation_id: UUID,
        message_id: UUID,
    ) -> ChatFeedbackDTO | None:
        doc = await self._feedback.find_one(
            {
                "conversation_id": str(conversation_id),
                "message_id": str(message_id),
            },
        )
        if doc is None:
            return None
        return ChatFeedbackDTO(
            conversation_id=UUID(doc["conversation_id"]),
            message_id=UUID(doc["message_id"]),
            workspace_id=UUID(doc["workspace_id"]),
            user_id=UUID(doc["user_id"]),
            feedback=doc["feedback"],
            created_at=doc["created_at"],
        )

    # --- Indexes ---

    async def ensure_indexes(self) -> None:
        await self._conversations.create_index(
            [("workspace_id", 1), ("owner_id", 1), ("updated_at", -1)],
            name="idx_conv_workspace_owner",
        )
        await self._conversations.create_index(
            "conversation_id",
            unique=True,
            name="idx_conv_id",
        )
        # Covers the folder-view query + its updated_at desc sort. Renamed from
        # idx_conv_folder (different keys, same name would error); drop the old
        # index manually on dev DBs.
        await self._conversations.create_index(
            [("workspace_id", 1), ("owner_id", 1), ("folder_id", 1), ("updated_at", -1)],
            name="idx_conv_folder_recency",
        )
        await self._folders.create_index(
            "folder_id",
            unique=True,
            name="idx_folder_id",
        )
        # Renamed from idx_folder_workspace_owner_name (now unique, same name
        # would error); drop the old index manually on dev DBs.
        await self._folders.create_index(
            [("workspace_id", 1), ("owner_id", 1), ("name", 1)],
            unique=True,
            name="uniq_folder_owner_name",
        )
        await self._messages.create_index(
            [("conversation_id", 1), ("created_at", 1)],
            name="idx_msg_conv_time",
        )
        await self._summaries.create_index(
            "conversation_id",
            unique=True,
            name="idx_summary_conv_id",
        )
        await self._feedback.create_index(
            [("conversation_id", 1), ("message_id", 1), ("user_id", 1)],
            unique=True,
            name="idx_feedback_unique",
        )
        await self._feedback.create_index(
            [("workspace_id", 1), ("feedback", 1), ("created_at", -1)],
            name="idx_feedback_workspace",
        )
        log.info("chat.repo.indexes_created")


# --- Document <-> DTO Converters ---


def _utc(dt: datetime) -> datetime:
    # ponytail: Motor client is not tz_aware, so BSON datetimes come back naive;
    # re-attach UTC here rather than flip the shared client (other consumers
    # assume naive).
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def _surface_query(surface: ChatSurface) -> dict:
    """Mongo clause selecting one surface.

    RESEARCH matches documents with no ``surface`` at all: every conversation
    written before surfaces existed was created there, so absence is not
    unknown -- it is research, and treating it that way avoids a backfill.
    """
    if surface == ChatSurface.RESEARCH:
        return {"surface": {"$ne": str(ChatSurface.LITERATURE)}}
    return {"surface": str(surface)}


def _conversation_to_doc(conv: ConversationDTO) -> dict:
    return {
        "conversation_id": str(conv.conversation_id),
        "workspace_id": str(conv.workspace_id),
        "owner_id": str(conv.owner_id),
        "title": conv.title,
        "folder_id": str(conv.folder_id) if conv.folder_id else None,
        "created_at": conv.created_at,
        "updated_at": conv.updated_at,
        "message_count": conv.message_count,
        "model_used": conv.model_used,
        "is_archived": conv.is_archived,
        "surface": str(conv.surface),
    }


def _doc_to_conversation(doc: dict) -> ConversationDTO:
    return ConversationDTO(
        conversation_id=UUID(doc["conversation_id"]),
        workspace_id=UUID(doc["workspace_id"]),
        owner_id=UUID(doc["owner_id"]),
        title=doc.get("title"),
        folder_id=UUID(doc["folder_id"]) if doc.get("folder_id") else None,
        created_at=_utc(doc["created_at"]),
        updated_at=_utc(doc["updated_at"]),
        message_count=doc.get("message_count", 0),
        model_used=doc.get("model_used"),
        is_archived=doc.get("is_archived", False),
        surface=ChatSurface(doc.get("surface") or ChatSurface.RESEARCH),
    )


def _folder_to_doc(folder: ChatFolderDTO) -> dict:
    return {
        "folder_id": str(folder.folder_id),
        "workspace_id": str(folder.workspace_id),
        "owner_id": str(folder.owner_id),
        "name": folder.name,
        "created_at": folder.created_at,
        "updated_at": folder.updated_at,
    }


def _doc_to_folder(doc: dict) -> ChatFolderDTO:
    return ChatFolderDTO(
        folder_id=UUID(doc["folder_id"]),
        workspace_id=UUID(doc["workspace_id"]),
        owner_id=UUID(doc["owner_id"]),
        name=doc["name"],
        created_at=_utc(doc["created_at"]),
        updated_at=_utc(doc["updated_at"]),
    )


def _message_to_doc(msg: ChatMessageDTO) -> dict:
    doc: dict = {
        "conversation_id": str(msg.conversation_id),
        "message_id": str(msg.message_id),
        "role": msg.role,
        "content": msg.content,
        "created_at": msg.created_at,
    }
    if msg.structured_content:
        doc["structured_content"] = [b.model_dump(mode="json") for b in msg.structured_content]
    if msg.sources:
        doc["sources"] = [s.model_dump(mode="json") for s in msg.sources]
    if msg.agent_trace:
        doc["agent_trace"] = msg.agent_trace.model_dump(mode="json")
    if msg.token_usage:
        doc["token_usage"] = msg.token_usage.model_dump(mode="json")
    if msg.query_context:
        doc["query_context"] = msg.query_context.model_dump(mode="json")
    return doc


def _doc_to_message(doc: dict) -> ChatMessageDTO:
    sources = [SourceCitationDTO(**s) for s in doc.get("sources", [])]
    structured_content = None
    if doc.get("structured_content"):
        structured_content = [ContentBlockDTO(**b) for b in doc["structured_content"]]
    agent_trace = None
    if doc.get("agent_trace"):
        agent_trace = AgentTraceDTO(**doc["agent_trace"])
    token_usage = None
    if doc.get("token_usage"):
        token_usage = TokenUsageDTO(**doc["token_usage"])
    query_context = None
    if doc.get("query_context"):
        query_context = QueryContextDTO(**doc["query_context"])

    return ChatMessageDTO(
        conversation_id=UUID(doc["conversation_id"]),
        message_id=UUID(doc["message_id"]),
        role=doc["role"],
        content=doc["content"],
        structured_content=structured_content,
        sources=sources,
        agent_trace=agent_trace,
        token_usage=token_usage,
        query_context=query_context,
        created_at=_utc(doc["created_at"]),
    )
