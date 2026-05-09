import logging

import asyncpg

from config import Config
from events import CommandExecuted

logger = logging.getLogger(__name__)


class DatabaseClient:
    def __init__(self):
        self._pool: asyncpg.Pool | None = None

    # ── Conexão ───────────────────────────────────────────────────

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            database=Config.DB_NAME,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            min_size=2,
            max_size=10,
            timeout=5,
        )
        logger.info("Pool de conexões com PostgreSQL estabelecido.")

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close()

    # ── Subscriber ────────────────────────────────────────────────

    async def handle_event(self, event: CommandExecuted) -> None:
        """Recebe CommandExecuted e persiste o estado no banco."""
        await self.update_led(event.led_id, event.toggled)
        await self.log_event(event.led_id, event.toggled, event.confirmed_by_plc)

    # ── Leitura ───────────────────────────────────────────────────

    async def get_all_leds(self) -> list[dict]:
        sql = "SELECT id, toggled FROM leds ORDER BY id ASC"
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(sql)
                return [dict(row) for row in rows]
        except asyncpg.PostgresError as e:
            logger.error(f"Erro ao buscar LEDs: {e}")
            return []

    async def get_led(self, led_id: int) -> dict | None:
        sql = "SELECT id, toggled FROM leds WHERE id = $1"
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(sql, led_id)
                return dict(row) if row else None
        except asyncpg.PostgresError as e:
            logger.error(f"Erro ao buscar LED {led_id}: {e}")
            return None

    # ── Escrita ───────────────────────────────────────────────────

    async def update_led(self, led_id: int, toggled: bool) -> bool:
        sql = "UPDATE leds SET toggled = $1, updated_at = NOW() WHERE id = $2"
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(sql, toggled, led_id)
            logger.info(f"LED {led_id} atualizado no banco → {'ON' if toggled else 'OFF'}")
            return True
        except asyncpg.PostgresError as e:
            logger.error(f"Erro ao atualizar LED {led_id}: {e}")
            return False

    async def log_event(self, led_id: int, toggled: bool, confirmed_by_plc: bool) -> bool:
        sql = """
            INSERT INTO led_events (led_id, toggled, confirmed_by_plc)
            VALUES ($1, $2, $3)
        """
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(sql, led_id, toggled, confirmed_by_plc)
            return True
        except asyncpg.PostgresError as e:
            logger.error(f"Erro ao registrar evento do LED {led_id}: {e}")
            return False

    async def sync_leds_from_plc(self, states: list[bool]) -> bool:
        sql = "UPDATE leds SET toggled = $1, updated_at = NOW() WHERE id = $2"
        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    for led_id, state in enumerate(states):
                        await conn.execute(sql, state, led_id)
            logger.info("Estado de todos os LEDs sincronizado com o CLP.")
            return True
        except asyncpg.PostgresError as e:
            logger.error(f"Erro ao sincronizar LEDs com o CLP: {e}")
            return False
