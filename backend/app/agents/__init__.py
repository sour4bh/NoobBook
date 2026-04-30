"""Agent runtime boundary.

`agents/runtime` owns provider-neutral model/tool orchestration contracts. It
does not own product tools, prompt content, persistence, provider SDK clients,
or domain behavior. Domains provide typed tools and prompts; providers translate
runtime requests to external APIs.
"""
