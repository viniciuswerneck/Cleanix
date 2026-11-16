# Design — Otimizador lote 3 (limpezas com prévia e confirmação)

## Objetivo
Adicionar ações de ganho de espaço no Otimizador que **sempre mostram uma
prévia** do que será removido e só executam após confirmação explícita (e
`pkexec` quando necessário).

## Escopo

### 1. Pacotes órfãos / kernels antigos (APT)
- Nova ação **“Pacotes não necessários (APT)”** em diálogo próprio.
- **Prévia (sem root):** `apt-get -s autoremove` (simulação). Extrai pacotes
  listados para remoção (`Remv`/linhas equivalentes) e espaço estimado a liberar
  (“freed/liberados”). Se nada a remover, informa claramente.
- **Remoção (com confirmação + `pkexec`):** `apt-get autoremove -y`.
- Substitui a entrada atual do Otimizador que fazia `apt-get autoremove -y &&
  apt-get clean` sem prévia. A limpeza de cache APT (`apt-get clean`) permanece
  como ação separada e simples (já com confirmação), pois não há lista granular
  útil além do cache.

### 2. Revisões antigas de Snap desativadas
- Nova ação **“Revisões antigas do Snap”** em diálogo próprio.
- **Prévia (sem root):** `snap list --all`; seleciona entradas com `disabled`
  nas notas e mostra nome, versão e revisão.
- **Remoção (com confirmação + `pkexec`):** para cada item selecionado/listado,
  `snap remove <name> --revision=<rev>`. Executa em sequência, acumula
  resultado/erros e relata ao final. Nada é removido se a lista estiver vazia.

### 3. Runtimes Flatpak sem uso
- Nova ação **“Runtimes Flatpak não usados”** em diálogo próprio.
- **Prévia (sem root, best effort):** executa `flatpak uninstall --unused`
  respondendo “não” automaticamente (stdin) para obter a lista; faz parsing das
  referências/runtimes exibidos. Se não houver itens, informa “nenhum runtime
  não usado”. Se o formato não puder ser interpretado com segurança, mostra a
  saída bruta e ainda exige confirmação antes de qualquer remoção.
- **Remoção (com confirmação, sem root por padrão):** `flatpak uninstall --unused -y`
  executado como usuário (flatpak gerencia instalações do usuário/sistema
  conforme configurado; não força `pkexec` a menos que falhe por permissão —
  nesse caso relata erro). Pré-requisito é sempre a prévia exibida.

## UX e segurança
- Cada diálogo mostra: estado da varredura, lista/contagem do que será removido,
  e um botão **Remover** desabilitado quando não há nada a remover.
- Confirmação explícita antes de executar, com resumo (“Remover N itens…”).
- Comandos executados via `execute_command`/`pkexec` como já existe; erros não
  interrompem silenciosamente e são mostrados ao usuário.
- Parsing tolerante a variações de idioma/saída; na dúvida prefere não remover
  sem mostrar informação.

## Implementação
- `cleanix/optimizer.py` (novo): funções puras/auxiliares `preview_apt_autoremove()`,
  `parse_apt_autoremove(text)`, `preview_snap_disabled()`, `parse_snap_disabled(text)`,
  `preview_flatpak_unused()`, `parse_flatpak_unused(text)` retornando estruturas
  com `items`, `summary/bytes` quando aplicável e `available/error`.
- `cleanix/dialogs.py`: diálogos `AptAutoremoveDialog`, `SnapCleanupDialog`,
  `FlatpakUnusedDialog` (varredura em thread, lista, confirmar+executar) e ajuste
  de `OPTIMIZER_ACTIONS`/`OptimizerDialog` para expor as novas ações e separar
  `apt-get clean`.
- `cleanix/locale/{pt_BR,en,es}.json`: textos das ações, prévias, estados vazios
  e confirmações.
- `tests/test_optimizer.py`: testes de parsing das saídas reais/variantes (APT
  com/sem pacotes, snap com disabled, flatpak com “nada” e com itens).

## Fora de escopo (lote 3)
- Remoção de kernels específicos individualmente, desinstalação de apps
  Flatpak/Snap instalados (apenas revisões desativadas/runtimes não usados),
  comparação de Raio-X, busca de arquivos grandes/duplicados e agendamento.
