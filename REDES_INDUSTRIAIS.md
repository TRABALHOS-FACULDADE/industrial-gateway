# Gateway Industrial — Relação com a Disciplina de Redes Industriais

## 1. Introdução

Este projeto implementa um **gateway de automação industrial** que integra três camadas tecnológicas distintas: uma interface de supervisão (Grafana), uma API de controle (FastAPI/Python) e um Controlador Lógico Programável (CLP Altus XP340). A comunicação entre o gateway e o CLP é realizada exclusivamente via **protocolo Modbus TCP**, tornando o projeto uma aplicação direta dos conceitos estudados na disciplina de Redes Industriais.

O objetivo prático é controlar 8 saídas digitais do CLP (mapeadas como LEDs) a partir de comandos HTTP, com registro histórico de todos os eventos em banco de dados relacional.

---

## 2. Redes Industriais e o Modelo de Automação

A disciplina de Redes Industriais trata dos protocolos e arquiteturas de comunicação utilizados em ambientes de manufatura e controle de processos. Diferentemente das redes corporativas (Ethernet/TCP-IP genérico), as redes industriais são projetadas com requisitos específicos:

- **Determinismo temporal**: respostas em tempo previsível
- **Robustez**: operação em ambientes com ruído elétrico, vibrações e temperaturas extremas
- **Interoperabilidade**: equipamentos de fabricantes distintos comunicando-se por protocolo padronizado
- **Confiabilidade**: tolerância a falhas sem perda de controle do processo

O projeto se posiciona na **camada de campo** do modelo hierárquico de automação (Modelo de Purdue), onde dispositivos de controle (CLPs) se comunicam com sistemas supervisórios via protocolo padronizado.

```
┌──────────────────────────────────┐
│  Nível 4 — Corporativo (ERP)     │
├──────────────────────────────────┤
│  Nível 3 — Supervisório (SCADA)  │  ← Grafana + PostgreSQL
├──────────────────────────────────┤
│  Nível 2 — Controle (Gateway)    │  ← FastAPI + Modbus TCP
├──────────────────────────────────┤
│  Nível 1 — Campo (CLP)           │  ← Altus XP340
├──────────────────────────────────┤
│  Nível 0 — Processo (Atuadores)  │  ← LEDs / Saídas Digitais
└──────────────────────────────────┘
```

---

## 3. Protocolo Modbus

### 3.1 Histórico e Contexto

O Modbus foi criado em 1979 pela Modicon (hoje Schneider Electric) como protocolo de comunicação serial para CLPs. É um dos protocolos mais antigos e ainda mais utilizados na automação industrial, graças à sua simplicidade, abertura (sem royalties) e ampla adoção pela indústria.

O protocolo define três variantes principais:

| Variante       | Meio Físico         | Encoding  | Uso típico                        |
|----------------|---------------------|-----------|-----------------------------------|
| Modbus RTU     | RS-232 / RS-485     | Binário   | Comunicação serial ponto-a-ponto  |
| Modbus ASCII   | RS-232 / RS-485     | ASCII     | Debugging, sistemas legados       |
| **Modbus TCP** | **Ethernet/TCP-IP** | **Binário** | **Redes industriais modernas**  |

Este projeto utiliza **Modbus TCP**, que encapsula o protocolo Modbus sobre TCP/IP, permitindo comunicação via rede Ethernet padrão — característica central da convergência entre redes industriais e corporativas.

### 3.2 Modelo Mestre-Escravo

O Modbus opera no modelo **mestre-escravo** (ou cliente-servidor no contexto TCP):

- **Mestre (Cliente)**: inicia todas as transações. No projeto, é o gateway Python.
- **Escravo (Servidor)**: responde às requisições. No projeto, é o CLP Altus XP340.

O escravo nunca transmite dados espontaneamente — apenas responde a requisições do mestre. Isso garante controle total sobre o tráfego de rede.

### 3.3 Modelo de Dados do Modbus

O Modbus organiza os dados do dispositivo escravo em quatro tabelas de memória:

| Tipo           | Acesso        | Tamanho | Endereçamento | Uso no projeto       |
|----------------|---------------|---------|---------------|----------------------|
| **Coils**      | Leitura/Escrita | 1 bit  | 0x0000–0xFFFF | Saídas digitais (LEDs) |
| Discrete Inputs | Somente leitura | 1 bit | 0x0000–0xFFFF | Entradas digitais     |
| Holding Registers | Leitura/Escrita | 16 bits | 0x0000–0xFFFF | Parâmetros, setpoints |
| Input Registers | Somente leitura | 16 bits | 0x0000–0xFFFF | Medições analógicas   |

O projeto utiliza exclusivamente **Coils** — cada LED mapeado diretamente para um Coil de mesmo endereço:

```
LED 0  →  Coil 0   (endereço 0x0000)
LED 1  →  Coil 1   (endereço 0x0001)
...
LED 7  →  Coil 7   (endereço 0x0007)
```

### 3.4 Estrutura do Frame Modbus TCP

O Modbus TCP encapsula a PDU (Protocol Data Unit) do Modbus dentro de um cabeçalho chamado **MBAP (Modbus Application Protocol Header)**:

```
┌──────────────────────────────────────────────────────────────┐
│                    Modbus TCP Frame                          │
├────────────────────────────┬─────────────────────────────────┤
│      MBAP Header (7 B)     │         PDU (N bytes)           │
├──────┬──────┬────────┬─────┼──────────┬──────────────────────┤
│ TID  │ PID  │ Length │ UID │ Func Code│ Data                 │
│ 2 B  │ 2 B  │  2 B   │ 1 B│   1 B    │ variável             │
└──────┴──────┴────────┴─────┴──────────┴──────────────────────┘

TID  = Transaction Identifier (correlaciona req/resp)
PID  = Protocol Identifier (sempre 0x0000 para Modbus)
UID  = Unit Identifier (endereço do escravo — Unit ID 1 neste projeto)
```

### 3.5 Function Codes Utilizados no Projeto

#### FC 0x01 — Read Coils

Usado para **confirmar o estado real da saída** após a escrita, verificando se o CLP efetivamente aplicou o comando.

**Requisição (gateway → CLP):**
```
TID    PID    Length  UID   FC    Start Addr  Quantity
00 01  00 00  00 06   01    01    00 00       00 01
                                  └─ Coil 0  └─ 1 coil
```

**Resposta (CLP → gateway):**
```
TID    PID    Length  UID   FC    Byte Count  Coil Data
00 01  00 00  00 04   01    01    01          01
                                              └─ Coil ON (bit 0 = 1)
```

#### FC 0x05 — Write Single Coil

Usado para **acionar ou desligar uma saída digital** do CLP.

**Requisição — Ligar LED 3 (gateway → CLP):**
```
TID    PID    Length  UID   FC    Coil Addr   Value
00 02  00 00  00 06   01    05    00 03       FF 00
                             └─ LED 3        └─ ON (0xFF00 = ligado)
```

**Requisição — Desligar LED 3:**
```
TID    PID    Length  UID   FC    Coil Addr   Value
00 03  00 00  00 06   01    05    00 03       00 00
                                              └─ OFF (0x0000 = desligado)
```

**Resposta:** o CLP ecoa a mesma requisição como confirmação.

---

## 4. Implementação Modbus no Projeto

### 4.1 Stack Tecnológica

O gateway utiliza a biblioteca **pymodbus 3.x** com cliente assíncrono:

```python
# gateway/modbus_client/modbus_client.py
from pymodbus.client import AsyncModbusTcpClient

self._client = AsyncModbusTcpClient(
    host=Config.PLC_HOST,   # 192.168.15.1
    port=Config.PLC_PORT,   # 502
    timeout=2,              # 2s — falha rápida, sem travar a API
    retries=1,              # 1 retry — equilíbrio entre robustez e latência
)
```

A escolha por cliente **assíncrono** (`AsyncModbusTcpClient`) é fundamental: permite que a API FastAPI continue atendendo outras requisições enquanto aguarda a resposta do CLP, sem bloquear o event loop.

### 4.2 Fluxo de Comunicação Completo

Cada comando enviado pelo operador no Grafana percorre o seguinte caminho:

```
[Grafana] POST /leds/3/on
    │
    ▼
[FastAPI] publica CommandRequested(led_id=3, toggled=True)
    │
    ▼
[ModbusClient] write_coil(address=3, value=True, slave=1)
    │   └─► Modbus TCP FC 05 → CLP Altus XP340 :502
    │        CLP aplica True na saída digital Q3
    │
    ▼
[ModbusClient] read_coil(address=3, slave=1)
    │   └─► Modbus TCP FC 01 → CLP Altus XP340 :502
    │        CLP retorna estado atual do Coil 3
    │
    ▼
[ModbusClient] publica CommandExecuted(confirmed_by_plc=True, success=True)
    │
    ├──► [DatabaseClient] UPDATE leds SET toggled=True WHERE id=3
    │                      INSERT INTO led_events (confirmed_by_plc=True)
    │
    ▼
[FastAPI] responde HTTP 200 { "id": 3, "toggled": true, "confirmed_by_plc": true }
    │
    ▼
[Grafana] atualiza tabela de estado via polling PostgreSQL (5s)
```

### 4.3 Confirmação por Leitura (Read-Back)

Uma característica importante da implementação é a **confirmação por leitura**. Após escrever no Coil, o gateway realiza uma leitura do mesmo endereço para verificar o estado real aplicado pelo CLP:

```python
# Escreve no CLP
success = await self._write_coil(event.led_id, event.toggled)

# Confirma lendo o estado atual
actual_state = await self._read_coil(event.led_id)
confirmed = actual_state is not None
final_state = actual_state if confirmed else event.toggled
```

Isso reflete uma prática comum em automação industrial: nunca assumir que o atuador executou o comando — sempre verificar o feedback do hardware. O campo `confirmed_by_plc` na tabela `led_events` registra se a confirmação foi obtida.

### 4.4 Tratamento de Falhas de Comunicação

O protocolo Modbus não define mecanismo de reconexão automática. O gateway implementa reconexão sob demanda:

```python
async def _write_coil(self, address: int, value: bool) -> bool:
    if not self.is_connected:
        if not await self.connect():   # tenta reconectar
            return False               # falha → publica CommandExecuted(success=False)
    try:
        result = await self._client.write_coil(...)
        if result.isError():           # Modbus exception response
            return False
        return True
    except ModbusException as e:       # timeout, connection reset, etc.
        return False
```

Quando o CLP não está acessível (ex: durante desenvolvimento sem o hardware), a API continua operando — o comando é registrado na tabela `led_events` com a mensagem de erro e o estado em `leds` não é alterado, preservando a integridade dos dados.

### 4.5 Parâmetros de Rede e Configuração

| Parâmetro       | Valor            | Justificativa                                          |
|-----------------|------------------|--------------------------------------------------------|
| `PLC_HOST`      | `192.168.15.1`   | IP fixo do CLP na rede local da universidade           |
| `PLC_PORT`      | `502`            | Porta padrão Modbus TCP (IANA registered)              |
| `PLC_UNIT_ID`   | `1`              | Unit ID do CLP (equivale ao endereço escravo Modbus)   |
| `timeout`       | `2s`             | Limite para resposta do CLP — evita bloqueio da API    |
| `retries`       | `1`              | Uma retentativa em caso de falha de transmissão        |

---

## 5. Arquitetura de Rede

### 5.1 Topologia

```
[Internet / Rede Corporativa]
          │
    ┌─────┴──────┐
    │   Switch   │
    └─────┬──────┘
          │ Ethernet (192.168.15.0/24)
    ┌─────┴──────────────────────────────┐
    │                                    │
[PC Host]                        [CLP Altus XP340]
192.168.15.x                     192.168.15.1:502
    │
    │ Docker bridge (industrial_net)
    ├── [gateway]  :8000  (FastAPI + Modbus Client)
    ├── [db]       :5432  (PostgreSQL)
    └── [grafana]  :3000  (Interface supervisória)
```

O gateway Python acessa o CLP via rede Ethernet padrão. O tráfego Modbus TCP segue o stack TCP/IP completo — não há camada de protocolo especial, o que simplifica a implantação mas requer que a rede seja adequadamente segmentada em ambientes de produção.

### 5.2 Segmentação por Docker Network

Os serviços internos (gateway, banco, Grafana) comunicam-se via rede Docker bridge `industrial_net`, isolados do acesso externo. Somente as portas necessárias são expostas ao host:

- `8000` → API REST (acesso do Grafana e ferramentas de debug)
- `3000` → Grafana (interface do operador)
- `5433` → PostgreSQL (acesso externo via PgAdmin, mapeado de 5432)

---

## 6. Relação com os Conceitos da Disciplina

| Conceito da Disciplina           | Aplicação no Projeto                                                |
|----------------------------------|---------------------------------------------------------------------|
| Protocolo Modbus e variantes     | Modbus TCP com `pymodbus` para controle de saídas digitais          |
| Modelo mestre-escravo            | Gateway Python (mestre) ↔ CLP Altus XP340 (escravo)                |
| Function Codes Modbus            | FC 01 (Read Coils) e FC 05 (Write Single Coil) usados explicitamente |
| Endereçamento de Coils           | Mapeamento direto LED N → Coil N (endereços 0 a 7)                  |
| MBAP Header e Unit ID            | `slave=Config.PLC_UNIT_ID` em todas as chamadas Modbus              |
| Modelo hierárquico de automação  | Projeto abrange campo (CLP), controle (gateway) e supervisório (Grafana) |
| Tratamento de falhas de rede     | Reconexão automática, timeout configurável, registro de erros        |
| Confirmação de estado            | Read-back após write — campo `confirmed_by_plc` no banco            |
| Integração OT/IT                 | Modbus TCP sobre Ethernet — convergência de redes industriais e corporativas |
| Supervisório e historização      | PostgreSQL para auditoria + Grafana para visualização em tempo real  |

---

## 7. Conclusão

O projeto demonstra na prática o ciclo completo de uma aplicação de automação industrial moderna: um operador interage com uma interface gráfica (Grafana), que dispara comandos para uma API Python, que por sua vez executa operações Modbus TCP diretamente sobre um CLP real. Cada camada corresponde a um nível do modelo hierárquico de automação, e o protocolo Modbus TCP é o elo entre o mundo do software (IP, HTTP, JSON) e o mundo do hardware industrial (saídas digitais, coils, sinais elétricos).

A escolha do Modbus TCP como protocolo de campo reflete a realidade da indústria: apesar de protocolos mais modernos existirem (PROFINET, EtherNet/IP, OPC-UA), o Modbus TCP permanece amplamente utilizado pela sua simplicidade, universalidade e pelo extenso parque instalado de equipamentos que o suportam — incluindo o CLP Altus XP340 utilizado neste projeto.
