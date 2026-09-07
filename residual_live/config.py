"""
residual_live.config
====================
Environment configuration loader for Confluent Cloud, Gemini ADK, and Web service.
"""

from pathlib import Path
import os
from dotenv import load_dotenv

# Search for .env in current directory, then parent directory (workspace root)
_current_dir = Path(__file__).resolve().parent
_product_dir = _current_dir.parent
_workspace_dir = _product_dir.parent

for _env_path in [
    _product_dir / ".env",
    _workspace_dir / ".env",
]:
    if _env_path.exists():
        load_dotenv(_env_path)
        break


class Settings:
    # Confluent Cloud Configuration
    CONFLUENT_BOOTSTRAP: str = os.getenv("CONFLUENT_BOOTSTRAP", "")
    CONFLUENT_API_KEY: str = os.getenv("CONFLUENT_API_KEY", "")
    CONFLUENT_API_SECRET: str = os.getenv("CONFLUENT_API_SECRET", "")
    CONFLUENT_TOPIC: str = os.getenv("CONFLUENT_TOPIC", "demo-events")
    CONFLUENT_OBLIGATIONS_TOPIC: str = os.getenv("CONFLUENT_OBLIGATIONS_TOPIC", "obligations")
    CONFLUENT_GROUP_ID: str = os.getenv("CONFLUENT_GROUP_ID", "residual-live-group")

    # Google Gemini / ADK Configuration
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.1-pro-preview")

    # IBM Bob Audit Metadata
    BOB_TASK_ID: str = "e1935a4d4dfe486aa3290acaa2f66f57"
    BOB_AUDIT_LEDGER: str = "bob-runs/coins-ledger.md"

    # Demo Key Authorization for state-mutating endpoints
    DEMO_KEY: str = os.getenv("DEMO_KEY", "residual-live-jury-2026")

    # Server Configuration
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    @classmethod
    def has_confluent_credentials(cls) -> bool:
        return bool(cls.CONFLUENT_BOOTSTRAP and cls.CONFLUENT_API_KEY and cls.CONFLUENT_API_SECRET)


settings = Settings()
