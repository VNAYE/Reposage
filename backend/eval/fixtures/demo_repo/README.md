# Demo repository

A miniature service used by RepoSage's evaluation harness. It exposes token
authentication, hybrid search fusion and a chat endpoint.

- `auth.py` - token creation and validation, password hashing
- `retrieval.py` - reciprocal rank fusion of vector and keyword results
- `config.py` - runtime settings
- `api.py` - chat request handler with authentication
