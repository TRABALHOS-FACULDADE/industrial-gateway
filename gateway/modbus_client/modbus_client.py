import logging

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from config import Config
from event_bus import EventBus
from events import CommandExecuted, CommandRequested

logger = logging.getLogger(__name__)


class ModbusClient:
    def __init__(self, bus: EventBus):
        self._client = AsyncModbusTcpClient(
            host=Config.PLC_HOST,
            port=Config.PLC_PORT,
            timeout=2,
            retries=1,
        )
        self._bus = bus
        self._simulated_coils = [False] * Config.TOTAL_LEDS

    # ── Conexão ───────────────────────────────────────────────────

    async def connect(self) -> bool:
        if Config.PLC_SIMULATION:
            logger.info("Modo simulado do CLP ativo; conexao Modbus real ignorada.")
            return True

        connected = await self._client.connect()
        if connected:
            logger.info(f"Modbus conectado — {Config.PLC_HOST}:{Config.PLC_PORT}")
        else:
            logger.error(f"Falha ao conectar ao CLP — {Config.PLC_HOST}:{Config.PLC_PORT}")
        return connected

    async def disconnect(self) -> None:
        if Config.PLC_SIMULATION:
            logger.info("Modo simulado do CLP encerrado.")
            return

        self._client.close()
        logger.info("Conexão Modbus encerrada.")

    @property
    def is_connected(self) -> bool:
        if Config.PLC_SIMULATION:
            return True
        return self._client.connected

    # ── Subscriber ────────────────────────────────────────────────

    async def handle_command(self, event: CommandRequested) -> None:
        """Recebe CommandRequested, executa no CLP e publica CommandExecuted."""
        success = await self._write_coil(event.led_id, event.toggled)

        if not success:
            await self._bus.publish(CommandExecuted(
                led_id=event.led_id,
                toggled=event.toggled,
                confirmed_by_plc=False,
                success=False,
                correlation_id=event.correlation_id,
                error=f"Sem comunicação com o CLP ({Config.PLC_HOST}:{Config.PLC_PORT})",
            ))
            return

        actual_state = await self._read_coil(event.led_id)
        confirmed = actual_state is not None
        final_state = actual_state if confirmed else event.toggled

        if not confirmed:
            logger.warning(
                f"Não foi possível confirmar LED {event.led_id} via leitura Modbus. "
                f"Usando valor enviado (otimista): {event.toggled}"
            )

        await self._bus.publish(CommandExecuted(
            led_id=event.led_id,
            toggled=final_state,
            confirmed_by_plc=confirmed,
            success=True,
            correlation_id=event.correlation_id,
        ))

    # ── Operações Modbus ──────────────────────────────────────────

    async def _write_coil(self, address: int, value: bool) -> bool:
        if Config.PLC_SIMULATION:
            self._simulated_coils[address] = value
            logger.info(f"Coil simulado {address} -> {'ON' if value else 'OFF'}")
            return True

        if not self.is_connected:
            logger.warning(f"Tentativa de escrita sem conexão (coil {address})")
            if not await self.connect():
                return False
        try:
            result = await self._client.write_coil(
                address=address,
                value=value,
                slave=Config.PLC_UNIT_ID,
            )
            if result.isError():
                logger.error(f"Erro Modbus ao escrever coil {address}: {result}")
                return False
            logger.info(f"Coil {address} → {'ON' if value else 'OFF'}")
            return True
        except ModbusException as e:
            logger.error(f"Exceção Modbus na escrita do coil {address}: {e}")
            return False

    async def _read_coil(self, address: int) -> bool | None:
        if Config.PLC_SIMULATION:
            state = self._simulated_coils[address]
            logger.debug(f"Coil simulado {address} lido -> {'ON' if state else 'OFF'}")
            return state

        if not self.is_connected:
            if not await self.connect():
                return None
        try:
            result = await self._client.read_coils(
                address=address,
                count=1,
                slave=Config.PLC_UNIT_ID,
            )
            if result.isError():
                logger.error(f"Erro Modbus ao ler coil {address}: {result}")
                return None
            state = bool(result.bits[0])
            logger.debug(f"Coil {address} lido → {'ON' if state else 'OFF'}")
            return state
        except ModbusException as e:
            logger.error(f"Exceção Modbus na leitura do coil {address}: {e}")
            return None

    async def read_all_coils(self, count: int = Config.TOTAL_LEDS) -> list[bool] | None:
        if Config.PLC_SIMULATION:
            return self._simulated_coils[:count]

        if not self.is_connected:
            if not await self.connect():
                return None
        try:
            result = await self._client.read_coils(
                address=0,
                count=count,
                slave=Config.PLC_UNIT_ID,
            )
            if result.isError():
                logger.error(f"Erro Modbus ao ler {count} coils: {result}")
                return None
            return [bool(result.bits[i]) for i in range(count)]
        except ModbusException as e:
            logger.error(f"Exceção Modbus na leitura em bloco: {e}")
            return None
