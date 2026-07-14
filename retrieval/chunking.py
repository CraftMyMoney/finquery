"""Chunking for KB markdown: ~400-token chunks, 15% overlap, H2 sections as
preferred boundaries. Frontmatter (title/refs/topics or publisher/page markers)
becomes chunk metadata for citations. Key-independent; embedding is not.
"""
