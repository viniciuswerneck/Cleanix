# Otimizador lote 3 — limpezas com prévia e confirmação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (native) to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Adicionar ao Otimizador remoção de pacotes órfãos (APT), revisões Snap desativadas e runtimes Flatpak não usados, sempre com prévia visível e confirmação antes de remover.

**Architecture:** `cleanix/optimizer.py` concentra parsing e prévias (comandos de simulação/listagem) retornando estruturas serializáveis e fáceis de testar. `cleanix/dialogs.py` adiciona três diálogos que varrem em thread, mostram a lista e executam a remoção apenas após confirmação, além de ajustar `OPTIMIZER_ACTIONS`. `pkexec` é usado onde a ação exige privilégios (APT, snap remove).

**Tech Stack:** Python 3, GTK4, `unittest`, comandos `apt-get -s`, `snap`, `flatpak`.

**Spec:** `docs/superpowers/specs/2026-11-16-cleanix-optimizer-lote3-design.md`

## Global Constraints
- Nunca remover sem listar/prever e sem confirmação explícita do usuário.
- APT autoremove e snap remove usam `pkexec`; flatpak unused roda como usuário (relatar erro se permissão falhar).
- Parsing tolerante a idioma (pt/en) e saídas vazias; na dúvida, não afirmar remoção segura sem mostrar informação.
- Não remover apps instalados, apenas pacotes órfãos APT, revisões Snap `disabled` e runtimes Flatpak não usados.

## Review Focus
- `apt-get -s autoremove` em português/inglês: detectar “nada a remover” e extrair pacotes quando houver `Remv`.
- `snap list --all`: linhas com `disabled` (inclusive `disabled,classic`) viram itens com name/version/rev; ativos ignorados.
- Flatpak: “Nada não usado…”/“Nothing unused…” => vazio; saída não interpretável não deve ser tratada como vazio silencioso.
- Falha parcial ao remover revisões Snap não interrompe todas sem relatório; erros aparecem ao usuário.
- Botão Remover desabilitado quando não há itens.

---

### Task 1: `cleanix/optimizer.py` — parsing e prévias

**Files:**
- Create: `cleanix/optimizer.py`
- Create: `tests/test_optimizer.py`

**Interfaces:**
- Produces:
  - `parse_apt_autoremove(text: str) -> dict` com `items` (lista de nomes), `freed_text`, `empty` (bool)
  - `preview_apt_autoremove() -> dict` com `available`, `items`, `freed_text`, `empty`, `error`, `output`
  - `parse_snap_disabled(text: str) -> list[dict]` itens `{name, version, rev, notes}`
  - `preview_snap_disabled() -> dict` com `available`, `items`, `error`
  - `parse_flatpak_unused(text: str) -> dict` com `items` (refs/linhas), `empty`, `unparsed`
  - `preview_flatpak_unused() -> dict` com `available`, `items`, `empty`, `unparsed`, `error`, `output`

- [x] **Step 1: Escrever testes que falham** em `tests/test_optimizer.py` cobrindo:
  - APT vazio (saída pt com “0 a serem removidos”) => `empty True`, sem itens.
  - APT com remoções: linhas `Remv linux-image-...` => itens extraídos.
  - Snap: header + linhas, apenas as com `disabled` viram itens; `brave ... disabled` e `code ... disabled,classic` incluídos.
  - Flatpak: “Nada não usado para desinstalar” => empty; “Nothing unused to uninstall” => empty.
- [x] **Step 2: Rodar `python3 -m unittest tests.test_optimizer -v` e ver falhar.**
- [x] **Step 3: Implementar `optimizer.py`** (parsers puros; prévias usam `shutil.which` e `execute_command`/subprocess simples sem root conforme spec).
- [x] **Step 4: Rodar testes e passar.**
- [x] **Step 5: Commit** `feat: adiciona parsing e prévias do otimizador`.

### Task 2: Diálogos de limpeza e ajuste do Otimizador

**Files:**
- Modify: `cleanix/dialogs.py`
- Modify: `cleanix/locale/{pt_BR,en,es}.json`
- Modify: `README.md`

**Interfaces:**
- Consumes: `cleanix.optimizer` previews/parsers e `execute_command`.
- Produces: `AptAutoremoveDialog`, `SnapCleanupDialog`, `FlatpakUnusedDialog`; `OPTIMIZER_ACTIONS` atualizado (autoremove em diálogo, `apt-get clean` separado) e integrado em `OptimizerDialog`.

- [x] **Step 1: Adicionar chaves i18n** (títulos, descrições, estados “verificando”, “nada a remover”, “remover N”, sucesso/erro, avisos) nas 3 línguas.
- [x] **Step 2: Implementar diálogos**: estado de carregamento, área/lista com itens, botão Remover desabilitado se vazio, confirmação (`confirm`) antes de executar; execução em thread com resultado via `GLib.idle_add`. Snap remove em loop por item com pkexec; flatpak remove com `flatpak uninstall --unused -y` como usuário.
- [x] **Step 3: Ajustar `OPTIMIZER_ACTIONS`/`OptimizerDialog`** e README (mencionar prévia e novas limpezas).
- [x] **Step 4: Verificação**: `python3 -m unittest discover -s tests -v`, `tools/check_language.py`, `tools/check_layout.py`.
- [x] **Step 5: Commit** `feat: adiciona limpezas do otimizador com prévia e confirmação`.

### Task 3: Fechamento

- [x] **Step 1:** Marcar plano concluído e atualizar ledger.
- [x] **Step 2:** Commit docs e `git push origin feat/funcionalidades-reais`.
