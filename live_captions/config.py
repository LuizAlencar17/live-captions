from __future__ import annotations

import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path

from dotenv import load_dotenv
from PySide6.QtCore import QSettings


@dataclass(frozen=True, slots=True)
class LanguageOption:
    label: str
    deepgram_code: str
    whisper_code: str


LANGUAGES: dict[str, LanguageOption] = {
    "pt": LanguageOption("Portuguese", "pt-BR", "pt"),
    "en": LanguageOption("English", "en-US", "en"),
}


@dataclass(frozen=True, slots=True)
class Settings:
    api_key: str | None
    whisper_model_path: Path
    sample_rate: int = 48_000
    frames_per_chunk: int = 4_800

    def with_api_key(self, api_key: str | None) -> Settings:
        return replace(self, api_key=api_key)


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def resolve_language(language_key: str) -> str:
    try:
        return LANGUAGES[language_key].deepgram_code
    except KeyError as exc:
        raise ValueError(f"Unsupported language: {language_key}") from exc


def resolve_whisper_language(language_key: str) -> str:
    try:
        return LANGUAGES[language_key].whisper_code
    except KeyError as exc:
        raise ValueError(f"Unsupported language: {language_key}") from exc


def get_saved_deepgram_api_key() -> str | None:
    """Retrieve the Deepgram API key stored in system settings (QSettings)."""
    settings = QSettings("Local", "Live Captions")
    val = settings.value("DEEPGRAM_API_KEY", None)
    if val is not None:
        val_str = str(val).strip()
        if val_str:
            return val_str
    return None


def save_deepgram_api_key(api_key: str) -> None:
    """Save the Deepgram API key to system settings and update the environment and .env."""
    cleaned = api_key.strip()
    settings = QSettings("Local", "Live Captions")
    if cleaned:
        settings.setValue("DEEPGRAM_API_KEY", cleaned)
        os.environ["DEEPGRAM_API_KEY"] = cleaned
    else:
        settings.remove("DEEPGRAM_API_KEY")
        os.environ.pop("DEEPGRAM_API_KEY", None)
    settings.sync()

    # Synchronize with .env file if available
    env_path = project_root() / ".env"
    if not env_path.exists() and getattr(sys, "frozen", False):
        fallback_env = Path(sys.executable).parent.parent / ".env"
        if fallback_env.exists():
            env_path = fallback_env

    try:
        if env_path.exists():
            content = env_path.read_text(encoding="utf-8")
            lines = content.splitlines()
            found = False
            new_lines = []
            for line in lines:
                if line.strip().startswith("DEEPGRAM_API_KEY="):
                    if cleaned:
                        new_lines.append(f'DEEPGRAM_API_KEY="{cleaned}"')
                    found = True
                else:
                    new_lines.append(line)
            if not found and cleaned:
                new_lines.append(f'DEEPGRAM_API_KEY="{cleaned}"')
            env_path.write_text("\n".join(new_lines) + ("\n" if new_lines else ""), encoding="utf-8")
        elif cleaned:
            env_path.write_text(f'DEEPGRAM_API_KEY="{cleaned}"\n', encoding="utf-8")
    except Exception:
        pass


def load_settings() -> Settings:
    env_path = project_root() / ".env"
    if not env_path.exists() and getattr(sys, "frozen", False):
        # Fallback para caso o usuário rode direto da pasta dist/ sem copiar o .env
        fallback_env = Path(sys.executable).parent.parent / ".env"
        if fallback_env.exists():
            env_path = fallback_env

    load_dotenv(env_path, override=True)

    # 1. Carrega do sistema (QSettings)
    api_key = get_saved_deepgram_api_key()
    if not api_key:
        # 2. Fallback para .env caso ainda não esteja salvo no sistema
        env_val = os.getenv("DEEPGRAM_API_KEY")
        if env_val and env_val.strip():
            api_key = env_val.strip()
            # Salva no sistema para próximas execuções
            save_deepgram_api_key(api_key)
        else:
            api_key = None

    model_value = os.getenv("WHISPER_MODEL_PATH", "models/small.pt").strip()
    model_path = Path(model_value)
    if not model_path.is_absolute():
        model_path = project_root() / model_path
    return Settings(api_key=api_key, whisper_model_path=model_path.resolve())
