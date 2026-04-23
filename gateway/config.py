import os

class Config:
    # Banco de Dados
    DB_HOST     = os.getenv("DB_HOST", "localhost")
    DB_PORT     = int(os.getenv("DB_PORT", 5432))
    DB_NAME     = os.getenv("DB_NAME", "industrial_db")
    DB_USER     = os.getenv("DB_USER", "scada_user")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")

    # CLP via Modbus TCP
    PLC_HOST    = os.getenv("PLC_HOST", "192.168.1.10")
    PLC_PORT    = int(os.getenv("PLC_PORT", 502))

    # Gateway
    POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 5)) # em segundos

    # Registros Modbus (Altus)
    REGISTER_TEMPERATURA  = 100
    REGISTER_PRESSAO      = 101
    REGISTER_SETPOINT     = 110

    # Coils
    COIL_BOMBA_LIGADA     = 0
    COIL_ALARME_ATIVO     = 1