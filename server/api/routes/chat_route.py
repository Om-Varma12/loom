from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException

from db.chat import ChatRepository
from db.schema.chat import ChatSessionItem, ChatSessionDetail
from db.database import database
from dependencies.auth_dep import CurrentUser, get_current_user

router = APIRouter(
    prefix="/chats",
    tags=["Chats"]
)

chat_repository = ChatRepository(database)


@router.get("/get-chat/{session_id}", response_model=ChatSessionDetail)
async def get_chat(
    session_id: UUID,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Returns the chat session details and its chronological messages.
    """
    conn = await database.get_conn()
    try:
        session = await chat_repository.get_chat_session_for_user(
            conn,
            str(session_id),
            current_user.id
        )
        if not session:
            raise HTTPException(status_code=404, detail="Chat session not found")
        
        messages = await chat_repository.get_chat_messages(conn, str(session_id))
        return {
            "session": session,
            "messages": messages
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch chat session: {str(e)}")
    finally:
        await database.release_conn(conn)


@router.post("/get-chats", response_model=list[ChatSessionItem])
async def get_chats(current_user: CurrentUser = Depends(get_current_user)):
    """
    Returns all chat sessions (id + title) for the current user,
    joined across all their projects, ordered by most recently updated.
    """
    conn = await database.get_conn()
    try:
        chats = await chat_repository.get_chats_by_user(conn, current_user.id)
        return chats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch chats: {str(e)}")
    finally:
        await database.release_conn(conn)
