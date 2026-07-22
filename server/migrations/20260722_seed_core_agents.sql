INSERT INTO agents (
    id,
    name,
    description,
    is_core,
    is_public,
    version,
    created_at,
    updated_at
)
VALUES
    ('204cfaf9-aa29-430f-9309-4a97e81e7791', 'FastAPI Agent', 'Fast API routing, validation, and async service scaffolding.', TRUE, TRUE, '1.0.0', NOW(), NOW()),
    ('ee1b6b17-a05d-4e4f-a313-cdae446f62c0', 'Streamlit Agent', 'Rapid data apps, dashboards, and internal tools in minutes.', TRUE, TRUE, '1.0.0', NOW(), NOW()),
    ('fdcc23b6-0106-459e-8b0e-29072d34b28c', 'MongoDB Agent', 'Document modeling, indexes, and aggregation pipeline helpers.', TRUE, TRUE, '1.0.0', NOW(), NOW()),
    ('ef209bcf-caca-43d8-9d4d-33c47af59141', 'PostgreSQL Agent', 'Schemas, joins, query tuning, and migration-friendly workflows.', TRUE, TRUE, '1.0.0', NOW(), NOW()),
    ('7f52aad5-5292-436e-a7a7-e7056f0361bd', 'Redis Agent', 'Caching, queues, and ultra-fast key value primitives.', TRUE, TRUE, '1.0.0', NOW(), NOW()),
    ('8ac481f3-a4e9-4d95-b065-4726e7c1d0f8', 'Supabase Agent', 'Auth, database, storage, and realtime backend workflows.', TRUE, TRUE, '1.0.0', NOW(), NOW()),
    ('ea173cc5-68ce-4711-9428-a09039e61e41', 'LangGraph Agent', 'Stateful multi-step graphs for complex LLM workflows.', TRUE, TRUE, '1.0.0', NOW(), NOW()),
    ('4c38ec8e-b2b0-42c1-a78b-ded28fd14138', 'OpenAI Agent', 'Prompting, tool use, and model orchestration for app workflows.', TRUE, TRUE, '1.0.0', NOW(), NOW()),
    ('9d4bd9f2-263e-4f88-80c0-a83cd556f9de', 'Docker Agent', 'Container builds, image hygiene, and compose setups.', TRUE, TRUE, '1.0.0', NOW(), NOW()),
    ('00ac1046-fc5b-4c9b-a7a3-15f94545b1a2', 'GitHub Actions Agent', 'CI pipelines, automation, and release workflow helpers.', TRUE, TRUE, '1.0.0', NOW(), NOW()),
    ('4cb0bc25-7486-4fc8-823b-cb2475f0fdd5', 'Authentication Agent', 'Login flows, sessions, and secure access patterns.', TRUE, TRUE, '1.0.0', NOW(), NOW()),
    ('99fb18b4-39b7-4b9f-848f-ec8c8e1c17b0', 'RAG Agent', 'Retrieval, chunking, and answer-grounding workflows.', TRUE, TRUE, '1.0.0', NOW(), NOW()),
    ('fb64a956-f8af-43f9-b6c8-c3b46626ee8a', 'Pytest Agent', 'Test layout, fixtures, and clean Python test patterns.', TRUE, TRUE, '1.0.0', NOW(), NOW()),
    ('1f4ddc23-02c6-4e4a-8ca9-4b09bb37f198', 'Web Scraping Agent', 'Page parsing, selectors, and safe extraction workflows.', TRUE, TRUE, '1.0.0', NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    is_core = EXCLUDED.is_core,
    is_public = EXCLUDED.is_public,
    version = EXCLUDED.version,
    updated_at = NOW();
