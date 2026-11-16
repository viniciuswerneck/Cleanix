# Raio-X lote 4 — snapshots e comparação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (native) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Salvar snapshots do Raio-X e comparar dois estados para mostrar mudanças em programas, discos, sistema, BIOS/hardware e alertas.

**Architecture:** `xray.build_report_data` (extraído de `build_report_json`) gera o dict comparável/redigível. `cleanix/snapshots.py` persiste/lista/carrega snapshots em `~/.local/share/cleanix/snapshots/` e implementa `compare_snapshots`. `XRayDialog` ganha ações de salvar e comparar, com diálogo de comparação.

**Tech Stack:** Python 3, GTK4, JSON, `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-16-cleanix-xray-lote4-design.md`

## Global Constraints
- Snapshots e comparações respeitam redação de identificadores quando solicitado; operação local, sem rede.
- Tolerar snapshots antigos/parciais (campos ausentes, programas em tuplas).
- Limitar retenção de snapshots para evitar crescimento ilimitado.

## Review Focus
- Diff de programas detecta adicionados, removidos e mudança de versão por origem.
- Comparação não quebra com chaves ausentes (`smart_known`, `sensors`, `power`, etc.).
- Salvar snapshot não expõe identificadores quando “Ocultar identificadores” está ativo.

---

### Task 1: `build_report_data` e `cleanix/snapshots.py` (storage)

**Files:**
- Modify: `cleanix/xray.py`
- Create: `cleanix/snapshots.py`
- Test: `tests/test_snapshots.py`

**Interfaces:**
- `xray.build_report_data(...) -> dict` (mesmos args de json), `build_report_json` usa-o.
- `snapshots.snapshots_dir()`, `save_snapshot(data, directory=None) -> Path`, `list_snapshots(directory=None) -> list[dict]`, `load_snapshot(path) -> dict`.

- [ ] **Step 1:** testes para `build_report_data` (redação/meta) e para save/list/load com tempdir e limite.
- [ ] **Step 2:** implementar refactor + módulo.
- [ ] **Step 3:** testes passam.
- [ ] **Step 4:** commit.

### Task 2: `compare_snapshots`

**Files:**
- Modify: `cleanix/snapshots.py` (ou `xray.py`)
- Test: `tests/test_snapshots.py`

**Interfaces:**
- `compare_snapshots(old, new) -> dict` com seções `programs`, `disks`, `system`, `bios`, `hardware`, `alerts`, `summary`.

- [ ] **Step 1:** testes para programas add/remove/change, discos, updates, alertas, tolerância a ausentes.
- [ ] **Step 2:** implementar.
- [ ] **Step 3:** testes passam.
- [ ] **Step 4:** commit.

### Task 3: UI no Raio-X (salvar e comparar)

**Files:**
- Modify: `cleanix/dialogs.py`
- Modify: `cleanix/locale/{pt_BR,en,es}.json`
- Modify: `README.md`

- [ ] **Step 1:** adicionar chaves i18n e botões “Salvar snapshot”/“Comparar…” no `XRayDialog`.
- [ ] **Step 2:** implementar salvar (usa dados atuais + redação) e diálogo de comparação (lista snapshots, escolhe base/alvo, mostra diff textual).
- [ ] **Step 3:** verificação `unittest`, `check_language`, `check_layout`.
- [ ] **Step 4:** commit.

### Task 4: Fechamento

- [ ] Marcar plano, atualizar ledger, commit docs e `git push`.
