from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://finquery:finquery@localhost:5433/finquery"
    openai_api_key: str = ""
    # The cohort key grants gpt-5.4-mini, gpt-5.4-nano, text-embedding-3-small
    # (not the gpt-4o family the design doc assumed; recorded in the README
    # Failure Analysis). Judge/actor separation is prompt-level, not
    # model-family-level, until a stronger judge model is available.
    llm_model: str = "gpt-5.4-mini"
    embedding_model: str = "text-embedding-3-small"
    judge_model: str = "gpt-5.4-mini"
    # KB retrieval leg for search_finance_kb: sparse (key-free), dense, or
    # hybrid (dense + sparse via RRF). The eval ablation flips this, never the
    # model. Switch to hybrid once embeddings are backfilled.
    kb_retrieval_mode: str = "sparse"
    # Master switch for the PII gate at EVERY LLM boundary in both approaches
    # (serialized chunks at rest, tool outputs, user questions). Default on.
    # Off exists for the masked-vs-unmasked ablation; flipping it requires
    # re-running ingest.serialize_transactions, since Approach A chunks are
    # gated at ingest time, not query time.
    pii_masking: bool = True


settings = Settings()
