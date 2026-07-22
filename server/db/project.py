from db.database import Database


class ProjectRepository:
    def __init__(self, db: Database):
        self.db = db


    async def create_project(
        self,
        conn,
        user_id: str,
        name: str,
        description: str | None
    ):
        query = """
        INSERT INTO projects (
            user_id,
            name,
            description
        )
        VALUES (
            $1,
            $2,
            $3
        )
        RETURNING
            id,
            user_id,
            name,
            description,
            status,
            created_at,
            updated_at;
        """

        row = await conn.fetchrow(
            query,
            user_id,
            name,
            description
        )

        return dict(row)


    async def get_project_by_id(
        self,
        conn,
        project_id: str
    ):
        query = """
        SELECT *
        FROM projects
        WHERE id = $1
        """

        row = await conn.fetchrow(
            query,
            project_id
        )

        if not row:
            return None

        return dict(row)

    async def get_project_by_id_for_user(
        self,
        conn,
        project_id: str,
        user_id: str
    ):
        query = """
        SELECT *
        FROM projects
        WHERE id = $1
          AND user_id = $2
        """

        row = await conn.fetchrow(
            query,
            project_id,
            user_id
        )

        if not row:
            return None

        return dict(row)


    async def get_projects(
        self,
        conn,
        user_id: str
    ):
        query = """
        SELECT *
        FROM projects
        WHERE user_id = $1
        ORDER BY created_at DESC
        """

        rows = await conn.fetch(
            query,
            user_id
        )

        return [dict(row) for row in rows]
