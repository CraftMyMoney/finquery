"""Hybrid retrieval: dense (pgvector cosine, exact/flat scan) + sparse
(Postgres full-text ts_rank_cd; honestly named, it is not true BM25), merged
with Reciprocal Rank Fusion. Evaluated as an ablation against dense-only.
"""
