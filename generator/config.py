"""Конфигурация генератора.

Настройки читаются из переменных окружения (префиксы ``GENERATOR_*`` для самого
генератора и ``CLICKHOUSE_*`` для подключения к БД) и из файла ``.env``.

Конфигурация — единственная точка правды обо всех «ручках» системы.
Разделение на два объекта (генератор / БД) держит независимые группы
настроек отдельно — так же, как в эталонной платформе.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ClickHouseSettings(BaseSettings):
    """Подключение к ClickHouse (префикс ``CLICKHOUSE_*``)."""

    model_config = SettingsConfigDict(
        env_prefix="CLICKHOUSE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    host: str = Field(default="localhost")
    port: int = Field(default=8123, ge=1, le=65535)
    database: str = Field(default="grocery")
    user: str = Field(default="default")
    password: str = Field(default="")
    secure: bool = Field(default=False)
    connect_timeout: int = Field(default=10, ge=1)
    send_receive_timeout: int = Field(default=60, ge=1)

    def safe_repr(self) -> str:
        """Строка для логов — без пароля."""
        return (
            f"ClickHouse(host={self.host}, port={self.port}, db={self.database}, "
            f"user={self.user}, secure={self.secure})"
        )


class GeneratorSettings(BaseSettings):
    """Настройки генератора (префикс ``GENERATOR_*``)."""

    model_config = SettingsConfigDict(
        env_prefix="GENERATOR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Интенсивность и динамика -------------------------------------------
    interval_seconds: float = Field(
        default=2.0, gt=0.0, description="Пауза между тиками генерации, секунды"
    )
    batch_size: int = Field(
        default=20, ge=1, description="Максимум чеков в одном тике"
    )
    orders_per_minute: float = Field(
        default=60.0, gt=0.0,
        description="Базовая интенсивность потока, чеков в минуту (до сезонных множителей)",
    )
    seed: int = Field(default=42, description="Seed для воспроизводимости генерации")

    # --- Аномалии -------------------------------------------------------------
    anomaly_probability: float = Field(
        default=0.005, ge=0.0, le=1.0, description="Вероятность аномалии на чек"
    )
    anomaly_strength: float = Field(
        default=3.0, ge=0.0, description="Множитель силы аномалии"
    )

    # --- Справочники сети -------------------------------------------------------
    store_count: int = Field(default=6, ge=1, le=8, description="Сколько магазинов сети")
    product_count: int = Field(default=90, ge=10, description="Число SKU в каталоге")

    # --- Историческая подложка --------------------------------------------------
    backfill_hours: float = Field(
        default=24.0, ge=0.0,
        description="Сколько часов истории сгенерировать при пустой БД (0 — не генерировать)",
    )

    # --- Retry: устойчивость к отказам БД ----------------------------------------
    retry_max_attempts: int = Field(default=5, ge=1)
    retry_base_delay_seconds: float = Field(default=0.5, ge=0.0)
    retry_max_delay_seconds: float = Field(default=30.0, ge=0.0)
    retry_backoff_factor: float = Field(default=2.0, ge=1.0)

    # --- Служебное ---------------------------------------------------------------
    health_port: int = Field(default=8080, ge=1, le=65535)
    log_level: str = Field(default="INFO", description="Уровень логирования")


@dataclass(frozen=True, slots=True)
class Settings:
    """Единая точка доступа к конфигурации всего генератора."""

    generator: GeneratorSettings
    clickhouse: ClickHouseSettings


@lru_cache
def get_settings() -> Settings:
    """Возвращает синглтон настроек (кэшируется в рамках процесса)."""
    return Settings(generator=GeneratorSettings(), clickhouse=ClickHouseSettings())
