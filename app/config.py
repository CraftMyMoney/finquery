from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://finquery:finquery@localhost:5433/finquery"
    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    judge_model: str = "gpt-4o"
    # Master switch for the PII gate at EVERY LLM boundary in both approaches
    # (serialized chunks at rest, tool outputs, user questions). Default on.
    # Off exists for the masked-vs-unmasked ablation; flipping it requires
    # re-running ingest.serialize_transactions, since Approach A chunks are
    # gated at ingest time, not query time.
    pii_masking: bool = True


settings = Settings()
