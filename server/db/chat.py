import json

from db.database import Database


class ChatRepository:
    def __init__(self, db: Database):
        self.db = db

    async def get_chats_by_user(
        self,
        conn,
        user_id: str
    ):
        """
        Returns chat sessions (id + title) for all projects belonging to the given user,
        ordered by most recently updated first.
        """
        query = """
        SELECT cs.id, cs.title, cs.project_id, cs.created_at, cs.updated_at
        FROM chat_sessions cs
        INNER JOIN projects p ON p.id = cs.project_id
        WHERE p.user_id = $1
        ORDER BY cs.updated_at DESC
        """

        rows = await conn.fetch(query, user_id)
        return [dict(row) for row in rows]

    async def create_chat_session(
        self,
        conn,
        project_id: str,
        title: str
    ):
        """
        Creates a new chat session for a project.
        """
        query = """
        INSERT INTO chat_sessions (
            project_id,
            title
        )
        VALUES (
            $1,
            $2
        )
        RETURNING
            id,
            project_id,
            title,
            created_at,
            updated_at;
        """
        row = await conn.fetchrow(query, project_id, title)
        return dict(row)

    async def create_chat_messages(
        self,
        conn,
        messages: list[dict]
    ):
        """
        Inserts multiple chat messages under a session.
        asyncpg does NOT accept Python dicts for JSONB — content must be serialized
        to a JSON string and cast with ::jsonb.
        """
        query = """
        INSERT INTO chat_messages (
            session_id,
            role,
            message_type,
            content
        )
        VALUES (
            $1,
            $2,
            $3,
            $4::jsonb
        );
        """
        for msg in messages:
            content = msg["content"]
            # Serialize dict/list to JSON string for asyncpg JSONB compatibility
            if isinstance(content, (dict, list)):
                content = json.dumps(content)
            await conn.execute(
                query,
                msg["session_id"],
                msg["role"],
                msg["message_type"],
                content
            )

    async def touch_chat_session(
        self,
        conn,
        session_id: str
    ):
        query = """
        UPDATE chat_sessions
        SET updated_at = NOW()
        WHERE id = $1
        """
        await conn.execute(query, session_id)

    async def get_chat_session(
        self,
        conn,
        session_id: str
    ):
        """
        Returns a single chat session metadata by ID.
        """
        query = """
        SELECT id, project_id, title, created_at, updated_at
        FROM chat_sessions
        WHERE id = $1
        """
        row = await conn.fetchrow(query, session_id)
        return dict(row) if row else None

    async def get_chat_session_for_user(
        self,
        conn,
        session_id: str,
        user_id: str
    ):
        """
        Returns a single chat session only when its project belongs to the user.
        """
        query = """
        SELECT cs.id, cs.project_id, cs.title, cs.created_at, cs.updated_at
        FROM chat_sessions cs
        INNER JOIN projects p ON p.id = cs.project_id
        WHERE cs.id = $1
          AND p.user_id = $2
        """
        row = await conn.fetchrow(query, session_id, user_id)
        return dict(row) if row else None

    async def get_chat_messages(
        self,
        conn,
        session_id: str
    ):
        """
        Returns all messages in a chat session ordered by creation time.
        """
        query = """
        SELECT id, session_id, role, message_type, content, created_at
        FROM chat_messages
        WHERE session_id = $1
        ORDER BY created_at ASC
        """
        rows = await conn.fetch(query, session_id)
        res = []
        for r in rows:
            d = dict(r)
            # If the database returns the JSONB column as a string (rare with asyncpg, but safe), parse it.
            if isinstance(d["content"], str):
                try:
                    d["content"] = json.loads(d["content"])
                except Exception:
                    pass
            res.append(d)
        return res
