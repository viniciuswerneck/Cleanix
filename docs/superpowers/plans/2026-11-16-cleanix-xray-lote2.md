# Raio-X lote 2 — sensores, energia e histórico SMART

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (native) to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Adicionar leituras de temperatura/bateria ao Raio-X e ao histórico de saúde SMART, com alertas e persistência local.

**Architecture:** `systeminfo` ganha leitores best effort para `/sys/class/thermal`, `/sys/class/hwmon` e `/sys/class/power_supply` (testados com `tempdir`). `xray.collect_system` incorpora `sensors`/`power`, `build_alerts` considera limiares novos e o snapshot inclui `smart_known` lido de `cleanix.smart_history`. `SmartDialog` registra cada verificação e exibe aviso de degradação; HTML/JSON/CSV/resumo mostram os novos dados quando presentes.

**Tech Stack:** Python 3, GTK4, JSON local, `unittest`, sistema de arquivos `/sys` (somente leitura).

**Spec:** `docs/superpowers/specs/2026-11-16-cleanix-xray-lote2-design.md`

## Global Constraints
- Leituras de sensores/bateria nunca exigem root e devem falhar silenciosamente (devolver vazio/`None` quando ausentes).
- Identificadores sensíveis (seriais/UUID/MAC) não são coletados nem exibidos nos recursos deste lote; o histórico SMART usa `disk` e `model`.
- Nenhuma remoção automática; alertas são apenas informativos/avisos.
- Manter pt-BR, inglês e espanhol com as mesmas chaves.
- Funções devem tolerar snapshots/dados antigos sem os campos novos.

## Review Focus
- Sensores com arquivos ausentes, valores não numéricos ou temperaturas absurdas não quebram a coleta nem geram exceções.
- Cálculo de saúde da bateria usa `energy_full`/`energy_full_design` ou `charge_full*` e lida com zero/divisão por zero.
- Histórico SMART identifica disco por `name` e opcionalmente por `model`; entradas antigas continuam legíveis após schema novo.
- Diálogo SMART registra histórico apenas quando há resultado parseado; falhas de escrita no JSON não impedem exibir o resultado.
- Alertas novos aparecem somente quando os dados existem e ultrapassam os limiares definidos.

---

### Task 1: Leitores de sensores e bateria em `systeminfo`

**Files:**
- Modify: `cleanix/systeminfo.py`
- Test: `tests/test_systeminfo.py`

**Interfaces:**
- Produces: `read_thermal_temps(base_path='/sys/class/thermal') -> list[dict]` (type, temp_c), `read_hwmon_temps(base_path='/sys/class/hwmon') -> list[dict]` (name, label, temp_c), `collect_sensors(base_paths...) -> dict` com `summary` e `readings`, `read_power_supply(base_path='/sys/class/power_supply') -> dict` (present, summary, details fields) ou chaves vazias quando inexistente.

- [x] **Step 1: Escrever testes que falham** (usar tempdir para simular `/sys`).
- [x] **Step 2: Rodar testes, ver falhar.**
- [x] **Step 3: Implementar leitores best effort.**
- [x] **Step 4: Rodar testes, passar.**
- [x] **Step 5: Commit.**

### Task 2: Integrar sensores/bateria/alertas no Raio-X (`xray`)

**Files:**
- Modify: `cleanix/xray.py`
- Modify: `cleanix/locale/{pt_BR,en,es}.json`
- Test: `tests/test_xray.py`

**Interfaces:**
- Consumes: novos leitores de `systeminfo`.
- Produces: `collect_system()` inclui `sensors`, `power`; `build_alerts(..., sensors=None, power=None)` gera alertas de temperatura/saúde da bateria/ciclos; `collect_unprivileged` repassa.

- [x] **Step 1: Escrever testes que falham** para `build_alerts` com temperatura alta e bateria degradada, e para tolerância a campos novos ausentes.
- [x] **Step 2: Rodar, ver falhar.**
- [x] **Step 3: Implementar em `xray.py`, adicionar i18n.**
- [x] **Step 4: Rodar testes, passar.**
- [x] **Step 5: Commit.**

### Task 3: Histórico de saúde SMART (`smart_history`)

**Files:**
- Create: `cleanix/smart_history.py`
- Test: `tests/test_smart_history.py` (novo)

**Interfaces:**
- Produces: `history_path()`, `load_history(path=None)`, `record_check(disk, model, parsed, path=None)`, `last_for_disk(disk, model=None, path=None)`, `compare_previous(disk, model, parsed, path=None) -> dict|None` com `changed`, `messages`.

- [x] **Step 1: Testes para gravação, limite, comparação (overall piora, atributo crítico aumenta, sem mudança).**
- [x] **Step 2: Implementar módulo.**
- [x] **Step 3: Rodar testes.**
- [x] **Step 4: Commit.**

### Task 4: Dialog SMART registra e mostra aviso; `smart_known` no Raio-X

**Files:**
- Modify: `cleanix/dialogs.py`
- Modify: `cleanix/xray.py` (adicionar `collect_smart_known()` usando `systeminfo.physical_disks_for_smart` + `smart_history.last_for_disk`)
- Modify: `cleanix/locale/{pt_BR,en,es}.json`
- Test: `tests/test_xray.py` (smart_known)

**Interfaces:**
- Produces: `SmartDialog` chama `smart_history.record_check` e exibe mensagem de comparação; `collect_unprivileged` inclui `smart_known` (lista/por disco); alertas podem incluir aviso “SMART falhou” a partir de `smart_known` se desejado (documentar no plano a decisão mínima).

- [x] **Step 1: Testes para `collect_smart_known` e para integração básica.**
- [x] **Step 2: Implementar dialog + xray + i18n.**
- [x] **Step 3: Rodar testes.**
- [x] **Step 4: Commit.**

### Task 5: HTML/JSON/CSV/resumo e verificação final

**Files:**
- Modify: `cleanix/xray.py` (`build_report_html`, `build_report_json`, `build_report_csv`, `build_support_summary`)
- Modify: `cleanix/dialogs.py` (exibir sensores/energia/SMART conhecido no cartão Sistema, se aplicável)
- Modify: `README.md`
- Test: `tests/test_xray.py`

- [x] **Step 1: Testes cobrindo seções novas ausentes e presentes.**
- [x] **Step 2: Implementar montagem e UI.**
- [x] **Step 3: `python3 -m unittest discover -s tests -v`, `tools/check_language.py`, `tools/check_layout.py`.**
- [x] **Step 4: Commit e push.**
