# Lote 5 — Análise de espaço (arquivos grandes e duplicados)

> **For agentic workers:** Native execution, task-by-task with tests and commits.

**Goal:** Adicionar “Análise de espaço” para revisar arquivos/pastas grandes e duplicados em $HOME (ou pasta escolhida), sem apagar nada automaticamente (apenas abrir pasta).

**Architecture:** `cleanix/space.py` com varredura segura, cálculo de maiores itens e detecção de duplicados por tamanho+hash (cancelável). Diálogo GTK com execução em thread; entrada no menu lateral; i18n pt/en/es.

**Tech Stack:** Python 3, GTK4, hashlib/os, unittest.

**Spec:** `docs/superpowers/specs/2026-11-16-cleanix-space-analysis-lote5-design.md`

## Tasks
- [x] Task 1: `cleanix/space.py` — varredura segura (sem seguir symlinks), top arquivos/pastas grandes, helpers de formato.
- [x] Task 2: `cleanix/space.py` — detecção de duplicados por tamanho+hash em etapas (cancelável) + testes `tests/test_space.py`.
- [x] Task 3: UI `SpaceAnalysisDialog` (pasta, iniciar/cancelar, abas grandes/duplicados, abrir pasta) + entrada no menu/i18n + README.
- [x] Task 4: Verificação (`unittest`, `check_language`, `check_layout`), marcar plano, commit(s) e push.

## Constraints
- Sem remoção/limpeza automática; apenas revisão e “Abrir pasta”.
- Sem root; escopo acessível ao usuário, sem seguir symlinks.
- Varredura cancelável e em segundo plano.
