"""Application configuration."""

from dataclasses import dataclass


@dataclass
class Settings:
    retrieval_top_k: int = 10
    rerank_top_k: int = 6
    embedding_dim: int = 768
    request_timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls, env: dict[str, str]) -> "Settings":
        return cls(
            retrieval_top_k=int(env.get("RETRIEVAL_TOP_K", 10)),
            rerank_top_k=int(env.get("RERANK_TOP_K", 6)),
            embedding_dim=int(env.get("EMBEDDING_DIM", 768)),
        )
