import asyncio
import logging
import sys
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import Config
from event_bus import EventBus
from events import CommandExecuted, CommandRequested
from db_client.database_client import DatabaseClient
from modbus_client.modbus_client import ModbusClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("gateway.api")

bus = EventBus()
db = DatabaseClient()
modbus = ModbusClient(bus)

COMMAND_TIMEOUT = 5.0


# ── Lifespan ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    sync_task: asyncio.Task | None = None
    logger.info("════ Gateway Industrial iniciando ════")

    # Wiring: conecta os serviços ao Event Bus
    bus.subscribe(CommandRequested, modbus.handle_command)
    bus.subscribe(CommandExecuted, db.handle_event)

    try:
        await db.connect()
    except Exception as e:
        logger.critical(f"Falha ao conectar ao PostgreSQL: {e}")
        sys.exit(1)

    if await modbus.connect():
        logger.info("CLP Altus XP340 conectado via Modbus TCP.")
    else:
        logger.warning(
            "Não foi possível conectar ao CLP na inicialização. "
            "A API subirá, mas comandos Modbus falharão até o CLP estar acessível."
        )

    sync_task = asyncio.create_task(_sync_leds_from_plc_periodically())

    try:
        yield
    finally:
        if sync_task:
            sync_task.cancel()
            with suppress(asyncio.CancelledError):
                await sync_task

        await modbus.disconnect()
        await db.disconnect()
        logger.info("Gateway encerrado com segurança.")


async def _sync_leds_from_plc_periodically() -> None:
    while True:
        try:
            states = await modbus.read_all_coils()
            if states is not None:
                await db.sync_leds_from_plc(states)
        except Exception as e:
            logger.error(f"Falha na sincronizacao periodica do CLP: {e}")

        await asyncio.sleep(Config.PLC_SYNC_INTERVAL_SECONDS)


# ── App ───────────────────────────────────────────────────────────

app = FastAPI(
    title="Gateway Industrial — Altus XP340",
    description="API REST para controle de LEDs via Modbus TCP",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Schemas ───────────────────────────────────────────────────────

class LedCommandRequest(BaseModel):
    toggled: bool = Field(..., description="True para acender o LED, False para apagar.")


class LedResponse(BaseModel):
    id: int
    toggled: bool
    confirmed_by_plc: bool = Field(
        description="True se o estado foi confirmado por leitura direta do CLP."
    )


class LedListResponse(BaseModel):
    leds: list[dict]


# ── Rotas ─────────────────────────────────────────────────────────

@app.get("/leds", response_model=LedListResponse, summary="Lista o estado atual de todos os LEDs")
async def get_all_leds():
    leds = await db.get_all_leds()
    if not leds:
        raise HTTPException(status_code=500, detail="Erro ao consultar banco de dados.")
    return LedListResponse(leds=leds)


@app.get("/leds/{led_id}", response_model=LedResponse, summary="Retorna o estado de um LED específico")
async def get_led(led_id: int):
    _validate_led_id(led_id)
    led = await db.get_led(led_id)
    if led is None:
        raise HTTPException(status_code=404, detail=f"LED {led_id} não encontrado.")
    return LedResponse(id=led["id"], toggled=led["toggled"], confirmed_by_plc=False)


@app.post("/leds/{led_id}/on", response_model=LedResponse, summary="Acende um LED via Modbus TCP")
async def led_on(led_id: int):
    return await _execute_led_command(led_id, toggled=True)


@app.post("/leds/{led_id}/off", response_model=LedResponse, summary="Apaga um LED via Modbus TCP")
async def led_off(led_id: int):
    return await _execute_led_command(led_id, toggled=False)


@app.patch("/leds/{led_id}", response_model=LedResponse, summary="Acende ou apaga um LED via Modbus TCP")
async def set_led(led_id: int, body: LedCommandRequest):
    return await _execute_led_command(led_id, toggled=body.toggled)


async def _execute_led_command(led_id: int, toggled: bool) -> LedResponse:
    _validate_led_id(led_id)

    command = CommandRequested(led_id=led_id, toggled=toggled)
    future = bus.expect(command.correlation_id)

    await bus.publish(command)

    try:
        result: CommandExecuted = await asyncio.wait_for(future, timeout=COMMAND_TIMEOUT)
    except asyncio.TimeoutError:
        bus._pending.pop(command.correlation_id, None)
        await db.log_event(
            led_id=led_id,
            toggled=toggled,
            confirmed_by_plc=False,
            error=f"Timeout: sem resposta do CLP em {COMMAND_TIMEOUT}s",
        )
        raise HTTPException(
            status_code=504,
            detail=f"Timeout aguardando resposta do CLP para LED {led_id}.",
        )

    if not result.success:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao enviar comando Modbus para LED {led_id}. "
                   f"Verifique a conexão com o CLP ({Config.PLC_HOST}:{Config.PLC_PORT}).",
        )

    return LedResponse(
        id=led_id,
        toggled=result.toggled,
        confirmed_by_plc=result.confirmed_by_plc,
    )


@app.get("/health", summary="Health check da API e dependências")
async def health_check():
    database_ok = await db.is_healthy()
    return {
        "api": "ok",
        "database": "ok" if database_ok else "down",
        "plc_connected": modbus.is_connected,
        "plc_host": Config.PLC_HOST,
        "plc_port": Config.PLC_PORT,
        "plc_sync_interval_seconds": Config.PLC_SYNC_INTERVAL_SECONDS,
    }


# ── Helpers ───────────────────────────────────────────────────────

def _validate_led_id(led_id: int) -> None:
    if led_id < 0 or led_id >= Config.TOTAL_LEDS:
        raise HTTPException(
            status_code=422,
            detail=f"LED ID inválido: {led_id}. Valores aceitos: 0 a {Config.TOTAL_LEDS - 1}.",
        )
