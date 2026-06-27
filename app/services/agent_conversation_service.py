import time

from app.database import Database
from app.schemas.agent_conversation import (
    AgentConversationItem,
    AgentMessageItem,
    AgentReplyRequest,
)
from app.schemas.message import MessageCreateRequest
from app.services.agent_auth_service import AuthenticatedAgent
from app.services.message_service import MessageCommandService, MessageCreateResult


class ConversationForbidden(Exception):
    pass


class ConversationNotFound(Exception):
    pass


class AgentConversationService:
    def __init__(
        self,
        database: Database,
        message_service: MessageCommandService,
    ):
        self._database = database
        self._message_service = message_service

    def list_conversations(self, agent_area: str) -> list[AgentConversationItem]:
        with self._database.transaction() as connection:
            rows = connection.execute(
                """
                SELECT id, external_phone_number, contact_id, areas, status,
                       unread_count, last_message_preview, last_message_direction,
                       last_message_at
                FROM conversations
                WHERE status IN ('OPEN', 'CLOSED', 'ARCHIVED')
                  AND NULLIF(BTRIM(areas), '') = NULLIF(BTRIM(%s), '')
                ORDER BY last_message_at DESC NULLS LAST, updated_at DESC, id
                """,
                (agent_area,),
            ).fetchall()
        return [
            AgentConversationItem(
                id=row[0],
                externalPhoneNumber=row[1],
                contactId=row[2],
                areas=row[3],
                status=row[4],
                unreadCount=row[5],
                lastMessagePreview=row[6],
                lastMessageDirection=row[7],
                lastMessageAt=row[8],
            )
            for row in rows
        ]

    def list_messages(
        self,
        conversation_id: str,
        agent_area: str,
    ) -> list[AgentMessageItem]:
        self._ensure_access(conversation_id, agent_area)
        with self._database.transaction() as connection:
            rows = connection.execute(
                """
                SELECT id, conversation_id, direction, message_type, text_content,
                       state, from_phone_number, to_phone_number, created_at,
                       received_at, sent_at, delivered_at
                FROM messages
                WHERE conversation_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (conversation_id,),
            ).fetchall()
        return [
            AgentMessageItem(
                id=row[0],
                conversationId=row[1],
                direction=row[2],
                messageType=row[3],
                textContent=row[4],
                state=row[5],
                fromPhoneNumber=row[6],
                toPhoneNumber=row[7],
                createdAt=row[8],
                receivedAt=row[9],
                sentAt=row[10],
                deliveredAt=row[11],
            )
            for row in rows
        ]

    def mark_read(self, conversation_id: str, agent_area: str) -> None:
        self._ensure_access(conversation_id, agent_area)
        now = time.time_ns() // 1_000_000
        with self._database.transaction() as connection:
            connection.execute(
                """
                UPDATE conversations
                SET unread_count = 0,
                    updated_at = %s
                WHERE id = %s
                  AND NULLIF(BTRIM(areas), '') = NULLIF(BTRIM(%s), '')
                """,
                (now, conversation_id, agent_area),
            )

    def reply(
        self,
        conversation_id: str,
        agent: AuthenticatedAgent,
        request: AgentReplyRequest,
        idempotency_key: str,
    ) -> MessageCreateResult:
        conversation = self._load_reply_conversation(conversation_id, agent.areas)
        return self._message_service.create(
            MessageCreateRequest(
                phoneNumbers=[conversation[0]],
                text=request.text,
                deviceId=conversation[1],
                simNumber=conversation[2],
                conversationId=conversation_id,
                metadata={"source": "agent", "agentId": agent.id},
            ),
            idempotency_key,
        )

    def _load_reply_conversation(self, conversation_id: str, agent_area: str):
        self._ensure_access(conversation_id, agent_area)
        with self._database.transaction() as connection:
            return connection.execute(
                """
                SELECT external_phone_number, device_id, sim_number
                FROM conversations
                WHERE id = %s
                """,
                (conversation_id,),
            ).fetchone()

    def _ensure_access(self, conversation_id: str, agent_area: str) -> None:
        with self._database.transaction() as connection:
            allowed = connection.execute(
                """
                SELECT id
                FROM conversations
                WHERE id = %s
                  AND status IN ('OPEN', 'CLOSED', 'ARCHIVED')
                  AND NULLIF(BTRIM(areas), '') = NULLIF(BTRIM(%s), '')
                """,
                (conversation_id, agent_area),
            ).fetchone()
            if allowed is not None:
                return
            exists = connection.execute(
                """
                SELECT id
                FROM conversations
                WHERE id = %s
                  AND status IN ('OPEN', 'CLOSED', 'ARCHIVED')
                """,
                (conversation_id,),
            ).fetchone()
        if exists is not None:
            raise ConversationForbidden
        raise ConversationNotFound
