# Design — Raio-X lote 2 (sensores, energia e histórico SMART)

## Objetivo
Enriquecer o diagnóstico do Raio-X com temperatura/energia e dar memória à
verificação SMART, sempre com coleta best effort (sem travar quando algo não
existe) e sem expor identificadores sensíveis.

## Escopo

### 1. Temperatura e sensores (sem root, sem dependências obrigatórias)
- Ler temperaturas de `/sys/class/thermal/thermal_zone*` (`type`, `temp` em
  miligraus) e `/sys/class/hwmon/hwmon*/temp*_input` com `name`/`*_label`.
- Consolidar em `system['sensors']` com resumo (ex.: “CPU 49 °C”) e lista de
  leituras; ignorar leituras inválidas/zero sem sentido.
- Exibir no cartão/detalhes **Sistema** do Raio-X, no HTML/JSON/CSV/resumo e no
  snapshot.

### 2. Bateria e energia (sem root)
- Ler `/sys/class/power_supply/BAT*` e `AC*`: status, capacidade (%),
  `energy_full`/`energy_full_design` (ou `charge_full*`) para saúde estimada e
  `cycle_count` quando disponível.
- Consolidar em `system['power']` com resumo (ex.: “Bateria 100%, saúde 61%,
  0 ciclos, na tomada”).
- Exibir nas mesmas saídas do item 1.

### 3. Alertas novos
- `build_alerts` passa a receber também sensores e energia:
  - aviso se temperatura ≥ 85 °C;
  - aviso se saúde da bateria < 80% (quando calculável);
  - informação se bateria presente mas saúde < 60% ou ciclos muito altos (≥ 1000)
    — apenas quando dado existir.
- Alertas entram no diálogo e em todos os formatos de exportação (já suportado).

### 4. Histórico básico de saúde SMART
- Novo módulo `cleanix/smart_history.py` com arquivo próprio
  `~/.local/share/cleanix/smart_history.json` (não mistura com limpezas).
- Registro por verificação: `timestamp`, `disk` (nome), `model`, `overall`
  (`passed|failed|unknown`), e `critical` = mapa `{nome_atributo: raw}` dos
  atributos críticos (Reallocated_Sector_Ct, Current_Pending_Sector,
  Offline_Uncorrectable, Reported_Uncorrect, Reallocated_Event_Count).
- `record_check(disk, model, parsed)` chamado ao final de `SmartDialog._done`
  quando há resultado parseado; mantém últimas N entradas por disco (ex.: 20) e
  total limitado.
- `compare_previous(disk, model, parsed)` devolve aviso se `overall` piorou ou
  se algum atributo crítico aumentou em relação ao registro anterior do mesmo
  disco (casamento por `disk` e, quando disponível, `model`).
- **Diálogo SMART:** após a verificação, mostra aviso de degradação quando
  houver (“piorou desde a última verificação…”).
- **Raio-X (sem senha):** lê o último registro conhecido por disco físico
  (`physical_disks_for_smart`) e mostra no cartão de Sistema/Discos (resumo
  textual “SMART conhecido: passou/falhou/desconhecido”) e inclui no snapshot em
  `smart_known` para HTML/JSON/CSV/resumo — sem rodar `smartctl`.

## Privacidade e segurança
- Nenhum dado novo exige root; SMART continua sob demanda com `pkexec`.
- Seriais não são coletados nem exibidos; identificação por nome/modelo.
- Temperatura/bateria não são dados sensíveis; a opção de ocultar
  identificadores não se aplica a eles.

## Compatibilidade
- `collect_unprivileged`/snapshot ganham campos novos; funções de montagem de
  HTML/JSON/CSV/resumo e de alertas devem tolerar snapshots antigos sem esses
  campos.
- `parse_smartctl` e comandos SMART existentes permanecem válidos; só se adiciona
  registro/comparação.

## Fora de escopo (lote 2)
- Dependência de `lm-sensors`/`upower` CLI, gráfico de temperatura em tempo
  real, agendamento, remoções no Otimizador, comparação de snapshots do Raio-X
  e busca de arquivos grandes/duplicados.

## Testes
- Parsers/leitores de sensores e bateria com árvores `/sys` simuladas (tempdir).
- `build_alerts` com temperatura alta e bateria degradada.
- `smart_history`: gravação, limite, comparação (sem mudança, piora de overall,
  aumento de atributo crítico).
- HTML/JSON/CSV/resumo incluem sensores/energia/`smart_known` quando presentes e
  não quebram sem eles.
