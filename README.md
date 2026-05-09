# Gateway Industrial — Altus XP340

Sistema acadêmico de automação industrial que expõe uma **API REST (FastAPI)** para controlar LEDs físicos em um CLP Altus XP340 via protocolo **Modbus TCP**, com monitoramento e controle pelo **Grafana**.

## Equipe

- Alexandre
- Bruno Sales
- Eduardo Rodrigues
- Felipe Azevedo Ribeiro
- Gabriel Batista Reis
- Guilherme Chumbinho
- João Borges

---

## Arquitetura

```
[Operador]
    │ clica no botão
    ▼
[Grafana :3000]  ──── POST /leds/{id}/on ────►  [FastAPI :8000]
  cloudspout-button-panel                               │
                                               Event Bus Interno
                                               (asyncio.Queue)
                                                       │
                                          ┌────────────┴────────────┐
                                          ▼                         ▼
                                 [Serviço Modbus]          [Serviço de Logs]
                                 AsyncModbusTcpClient       asyncpg → PostgreSQL
                                          │
                                          ▼
                                 [CLP Altus XP340]
                                 192.168.15.1:502
                                 Saída Digital Qx → LED
```

O sistema usa uma arquitetura híbrida orientada a eventos: a API recebe o comando HTTP, publica um evento interno (`CommandRequested`) e aguarda a confirmação do hardware (`CommandExecuted`) antes de responder. Falhas de comunicação com o CLP são registradas no banco de dados com a mensagem de erro.

---

## Hardware

| Parâmetro        | Valor           |
|------------------|-----------------|
| Modelo do CLP    | Altus XP340     |
| IP do CLP        | 192.168.15.1    |
| Porta Modbus TCP | 502             |
| Unit ID Modbus   | 1               |
| Saídas digitais  | 8 (Coils 0–7)   |

---

## Pré-requisitos

- [Docker](https://www.docker.com/) e Docker Compose
- Arquivo `.env` configurado (ver abaixo)

---

## Como rodar

```bash
# 1. Configure o ambiente
cp .env.example .env
# Edite o .env com sua senha do banco

# 2. Suba tudo
docker compose up --build

# 3. Acesse
# Grafana:  http://localhost:3000  (admin / ver .env)
# API docs: http://localhost:8000/docs
# Health:   http://localhost:8000/health
```

> **Primeiro boot:** o banco de dados é inicializado automaticamente com o schema e os 8 LEDs via `sql/init.sql`.

> **Sem CLP disponível:** a API sobe normalmente. Comandos enviados pelos botões são registrados na tabela `led_events` com a mensagem de erro, mas não alteram o estado em `leds`.

---

## Variáveis de Ambiente

| Variável            | Descrição                        | Padrão              |
|---------------------|----------------------------------|---------------------|
| `DB_USER`           | Usuário do PostgreSQL            | `postgres`          |
| `DB_PASSWORD`       | Senha do PostgreSQL              | —                   |
| `DB_NAME`           | Nome do banco de dados           | `IndustrialGateway` |
| `PLC_HOST`          | IP do CLP Altus XP340            | `192.168.15.1`      |
| `PLC_PORT`          | Porta Modbus TCP                 | `502`               |
| `PLC_UNIT_ID`       | Unit ID Modbus                   | `1`                 |
| `GRAFANA_USER`      | Usuário admin Grafana            | `admin`             |
| `GRAFANA_PASSWORD`  | Senha admin Grafana              | —                   |

---

## Endpoints da API

| Método | Rota              | Descrição                              |
|--------|-------------------|----------------------------------------|
| `GET`  | `/leds`           | Lista estado atual dos 8 LEDs          |
| `GET`  | `/leds/{id}`      | Estado de um LED específico (0–7)      |
| `POST` | `/leds/{id}/on`   | Acende o LED via Modbus TCP            |
| `POST` | `/leds/{id}/off`  | Apaga o LED via Modbus TCP             |
| `PATCH`| `/leds/{id}`      | Controla o LED com body `{"toggled": bool}` |
| `GET`  | `/health`         | Status da API e conexão com o CLP      |

Documentação interativa disponível em `http://localhost:8000/docs`.

---

## Banco de Dados

### `leds` — estado atual
| Coluna       | Tipo        | Descrição                  |
|--------------|-------------|----------------------------|
| `id`         | INTEGER PK  | ID do LED (0–7)            |
| `toggled`    | BOOLEAN     | TRUE = aceso               |
| `updated_at` | TIMESTAMPTZ | Última atualização         |

### `led_events` — histórico de auditoria
| Coluna            | Tipo        | Descrição                              |
|-------------------|-------------|----------------------------------------|
| `id`              | BIGSERIAL PK| —                                      |
| `led_id`          | INTEGER     | Referencia `leds.id`                   |
| `toggled`         | BOOLEAN     | Estado solicitado                      |
| `confirmed_by_plc`| BOOLEAN     | Confirmado por leitura Modbus          |
| `error`           | TEXT        | Mensagem de erro (NULL se sucesso)     |
| `occurred_at`     | TIMESTAMPTZ | Timestamp do evento                    |

---

## Portas expostas

| Serviço    | Porta host | Descrição                        |
|------------|------------|----------------------------------|
| Grafana    | 3000       | Interface de controle            |
| Gateway    | 8000       | API REST                         |
| PostgreSQL | 5433       | Acesso externo (ex: PgAdmin)     |

> PostgreSQL expõe na porta **5433** para evitar conflito com instalações locais.
