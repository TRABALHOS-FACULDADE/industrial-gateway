import uuid
from dataclasses import dataclass, field


@dataclass
class CommandRequested:
    """Publicado pela API quando recebe um PATCH /leds/{id}."""
    led_id: int
    toggled: bool
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class CommandExecuted:
    """Publicado pelo Modbus após executar (ou falhar) o comando no CLP."""
    led_id: int
    toggled: bool
    confirmed_by_plc: bool
    success: bool
    correlation_id: str
    error: str | None = None
