"""
AI Agents - legacy migration source.

`web_agent_service` still lives in this package as
`app.services.ai_agents.web_agent_service`. The other former entries
(`email_agent_service`, `wireframe_agent_service`, plus the studio document
agents) moved to their domain homes under `app/studio/...` per NBB-504/505/506
and are imported from those homes directly. The previous re-export shims were
removed in NBB-706.
"""
