# Database Schema

---

## users

Stores user accounts.

| Column | Type | Constraints |
|----------|----------|----------|
| id | UUID | PK |
| clerk_user_id | TEXT | UNIQUE, nullable for legacy rows |
| email | TEXT | UNIQUE, NOT NULL |
| name | TEXT | NOT NULL |
| role | TEXT | DEFAULT 'user' |
| created_at | TIMESTAMP | DEFAULT NOW() |

### Relationships

- One user can create many agents.
- One user can own many projects.

---

## agents

Stores AI agents available in the marketplace.

| Column | Type | Constraints |
|----------|----------|----------|
| id | UUID | PK |
| name | TEXT | NOT NULL |
| description | TEXT | NULL |
| created_by | UUID | FK → users.id |
| is_core | BOOLEAN | DEFAULT FALSE |
| is_public | BOOLEAN | DEFAULT FALSE |
| version | TEXT | DEFAULT '1.0.0' |
| last_kb_update | TIMESTAMP | NULL |
| created_at | TIMESTAMP | DEFAULT NOW() |
| updated_at | TIMESTAMP | DEFAULT NOW() |

### Relationships

- Many agents can belong to one user.
- One agent can have many sources.
- One agent can be attached to many projects.

### Examples

- FastAPI Agent
- MongoDB Agent
- Redis Agent
- React Agent
- Documentation Agent

---

## agent_sources

Stores knowledge sources attached to agents.

| Column | Type | Constraints |
|----------|----------|----------|
| id | UUID | PK |
| agent_id | UUID | FK → agents.id |
| url | TEXT | NOT NULL |
| source_type | TEXT | NOT NULL |
| is_active | BOOLEAN | DEFAULT TRUE |
| last_scraped_at | TIMESTAMP | NULL |

### Relationships

- Many sources belong to one agent.

### Example Source Types

- website
- github
- docs
- pdf
- youtube

### Example URLs

- https://fastapi.tiangolo.com
- https://redis.io/docs
- https://github.com/langchain-ai/langgraph

---

## projects

Stores user-created projects.

| Column | Type | Constraints |
|----------|----------|----------|
| id | UUID | PK |
| user_id | UUID | FK → users.id |
| name | TEXT | NOT NULL |
| description | TEXT | NULL |
| status | TEXT | DEFAULT 'active' |
| created_at | TIMESTAMP | DEFAULT NOW() |
| updated_at | TIMESTAMP | DEFAULT NOW() |

### Relationships

- Many projects belong to one user.
- One project can contain many agents.
- One project can contain many chat sessions.

### Example Status Values

- active
- completed
- archived

---

## project_agents

Join table connecting projects and agents.

| Column | Type | Constraints |
|----------|----------|----------|
| project_id | UUID | PK, FK → projects.id |
| agent_id | UUID | PK, FK → agents.id |

### Relationships

- Many-to-many between projects and agents.

### Example

Project:

- Build SaaS Analytics Platform

Assigned Agents:

- FastAPI Agent
- PostgreSQL Agent
- React Agent
- Docker Agent

---

## chat_sessions

Stores conversation threads inside a project.

| Column | Type | Constraints |
|----------|----------|----------|
| id | UUID | PK |
| project_id | UUID | FK → projects.id |
| title | TEXT | NOT NULL |
| created_at | TIMESTAMP | DEFAULT NOW() |
| updated_at | TIMESTAMP | DEFAULT NOW() |

### Relationships

- Many chat sessions belong to one project.
- One chat session contains many messages.

### Example

Project: AI Job Hunt OS

Chats:

- Initial Build
- Resume Generator Feature
- AWS Deployment
- Bug Fixes

---

## chat_messages

Stores all messages, plans, execution results, and system events within a chat session.

| Column | Type | Constraints |
|----------|----------|----------|
| id | UUID | PK |
| session_id | UUID | FK → chat_sessions.id |
| role | TEXT | NOT NULL |
| message_type | TEXT | NOT NULL |
| content | JSONB | NOT NULL |
| created_at | TIMESTAMP | DEFAULT NOW() |

### Relationships

- Many messages belong to one chat session.

### Role Values

- user
- assistant
- agent
- system

### Message Type Values

- text
- task_plan
- agent_execution
- system_event

### Example Content

#### User Message

```json
{
  "text": "Build me a todo app"
}
