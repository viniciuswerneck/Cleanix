# Design — Raio-X lote 4 (snapshots e comparação)

## Objetivo
Permitir salvar o estado do Raio-X ao longo do tempo e comparar dois momentos
para ver o que mudou (programas, discos, atualizações, BIOS/hardware e alertas).

## Escopo

### 1. Snapshots salvos
- Novo módulo `cleanix/snapshots.py` para armazenar e listar snapshots em
  `~/.local/share/cleanix/snapshots/<timestamp>.json`.
- Formato: dados do inventário (equivalentes ao relatório) + metadados
  (`generated`, `cleanix_version`, `os`, `product`, `redacted`, rótulo
  opcional). Reutiliza a estrutura de dados do Raio-X (não depende do HTML).
- **Salvar:** no `XRayDialog`, botão **“Salvar snapshot”** grava o estado atual
  (incluindo detalhes privilegiados já carregados) respeitando a opção
  **“Ocultar identificadores”** (padrão ligado). Se detalhes privilegiados
  não foram carregados, salva com os dados básicos (como o relatório).
- **Listar:** listar snapshots salvos (mais recentes primeiro) com data e
  identificação básica (produto/SO).

### 2. Comparação
- Função pura `compare_snapshots(old, new)` (em `xray.py` ou `snapshots.py`)
  produzindo um diff estruturado:
  - **Programas:** por origem (apt/snap/flatpak) — adicionados, removidos e com
    versão alterada (chave por nome do pacote/app).
  - **Discos:** por `name`+`mount_point` — variação de uso/percentual quando
    comparável.
  - **Sistema:** mudança em atualizações pendentes; resumo/temperatura/bateria
    quando relevante.
  - **BIOS/Hardware/Produto:** mudanças de resumo/campos principais.
  - **Alertas:** alertas novos e resolvidos (comparação por texto).
- Comparação tolera snapshots parciais/antigos (campos ausentes).

### 3. Interface no Raio-X
- Botão **“Comparar…”** abre um diálogo de comparação:
  - permite escolher “snapshot salvo” ou “estado atual” como base e como alvo;
  - lista snapshots disponíveis;
  - mostra resultado em seções legíveis (contagens e listas curtas, com opção de
    ver detalhes).
- Fluxo simples para leigo: comparar o estado atual com o último snapshot salvo
  em um clique, além da escolha manual.

### 4. Exportação/privacidade
- Snapshots seguem a mesma redação de identificadores do momento do salvamento.
- Comparação não envia dados para fora; opera localmente.

## Implementação
- `cleanix/snapshots.py`: `snapshots_dir()`, `save_snapshot(data)`,
  `list_snapshots()`, `load_snapshot(path)`, limites de retenção razoáveis.
- `cleanix/xray.py` (ou `snapshots.py`): `snapshot_data(snapshot, ...)` para
  obter dict comparável/redigível e `compare_snapshots(old, new)`.
- `cleanix/dialogs.py`: ações “Salvar snapshot” e “Comparar…” no `XRayDialog`,
  diálogo de comparação.
- `cleanix/locale/{pt_BR,en,es}.json`: textos.
- `tests/test_snapshots.py` e/ou `tests/test_xray.py`: salvar/listar/carregar,
  diff de programas adicionados/removidos/atualizados, tolerância a dados
  ausentes.

## Fora de escopo (lote 4)
- Sincronização/nuvem, comparação de HTML exportado externamente (apenas
  snapshots salvos pelo app), busca de arquivos grandes/duplicados e agendamento.
