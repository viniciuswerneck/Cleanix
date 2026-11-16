# Design — Raio-X lote 1 (JSON/CSV e resumo para suporte)

## Objetivo
Entregar formas rápidas e seguras de compartilhar o inventário do Raio-X,
reaproveitando o snapshot, a coleta privilegiada e a opção de privacidade já
existentes.

## Escopo
1. **Exportar JSON**: arquivo `cleanix-raiox-AAAA-MM-DD.json` com o inventário
   completo (metadados, resumos, destaques, BIOS/hardware, rede, sistema, discos
   e programas com nome/versão/tamanho). Usa os mesmos dados do HTML.
2. **Exportar CSV**: arquivo `cleanix-raiox-AAAA-MM-DD.csv` com visão tabular
   para planilhas — programas (origem, nome, versão, tamanho) e, em seguida,
   discos (nome, tipo, total, usado, %, montagem) e alertas.
3. **Copiar resumo para suporte**: botão que copia para a área de transferência
   um texto curto (SO, produto/BIOS, CPU/RAM/discos, rede, atualizações,
   contagens de programas, alertas, versão do Cleanix e data).

## Privacidade e segurança
- A opção **“Ocultar identificadores”** do diálogo vale para HTML, JSON, CSV e
  resumo copiado.
- Quando ativa (padrão), aplica `redact_sensitive` em textos de BIOS/hardware e
  mascara MACs; números de série/UUID/SKU/Asset Tag não aparecem nos arquivos
  nem no resumo. Quando desmarcada, os dados completos são incluídos.
- Resumo para suporte usa sempre a redação ativa no momento da cópia.
- Nenhuma ação exige senha nova além do fluxo já existente para detalhes
  completos; JSON/CSV podem ser gerados com os dados já carregados e, se o
  usuário quiser incluir detalhes completos, reutiliza a mesma coleta com senha
  única do HTML.

## Implementação
- `cleanix/xray.py`: funções puras `build_report_json(...)` e
  `build_report_csv(...)`, além de `build_support_summary(...)` (texto), todas
  aceitando `redact=True` e reutilizando os mesmos helpers de redação.
- `cleanix/dialogs.py`: botão **“Copiar resumo”**; exportação passa a oferecer
  HTML e JSON/CSV (botões separados “Exportar JSON” e “Exportar CSV”, mesmo
  padrão de salvar/abrir pasta e mesma coleta privilegiada quando necessário).
- `cleanix/locale/{pt_BR,en,es}.json`: novas chaves `xray.export_json`,
  `xray.export_csv`, `xray.copy_summary`, `xray.summary_copied`, nomes de
  arquivo e textos do resumo.
- `tests/test_xray.py`: redação em JSON/CSV/resumo, estrutura JSON, CSV com
  origens/colunas, ausência de identificadores quando `redact=True` e presença
  quando `False`.

## Fora de escopo (lote 1)
- Comparação de snapshots, sensores/bateria, remoções no Otimizador,
  agendamento e busca de arquivos grandes/duplicados (lotes seguintes).
