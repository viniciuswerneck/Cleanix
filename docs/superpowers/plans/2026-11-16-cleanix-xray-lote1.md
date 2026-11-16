# Raio-X lote 1 — JSON, CSV e resumo para suporte

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (native) to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Permitir exportar o inventário do Raio-X em JSON e CSV e copiar um resumo curto para suporte, respeitando a opção de ocultar identificadores.

**Architecture:** `cleanix/xray.py` ganha funções puras (`build_support_summary`, `build_report_json`, `build_report_csv`) que recebem o snapshot e os textos privilegiados e aplicam a mesma redação usada no HTML. `cleanix/dialogs.py` adiciona o botão de copiar resumo e generaliza a exportação para HTML/JSON/CSV, reutilizando a coleta privilegiada única e a checkbox de privacidade. Testes em `tests/test_xray.py`.

**Tech Stack:** Python 3, GTK4, `json`, `csv`/formatação manual, `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-16-cleanix-xray-lote1-design.md`

## Global Constraints
- Nenhum identificador sensível (Serial Number, UUID, SKU Number, Asset Tag, linhas `serial:` e MACs) deve aparecer em JSON, CSV ou resumo quando `redact=True` (padrão). Quando `redact=False`, os valores originais devem aparecer.
- Todo conteúdo do sistema incluído em saídas textuais/JSON/CSV deve ser tratado como dado; o HTML continua escapando com `html.escape`.
- Ações administrativas continuam apenas via `pkexec` no fluxo já existente; nenhuma senha nova.
- Manter pt-BR, inglês e espanhol com as mesmas chaves.
- Funções de montagem devem tolerar snapshots parciais/antigos (chaves ausentes).

## Review Focus
- `redact=True` remove `Serial Number/UUID/SKU Number/Asset Tag/serial:` em qualquer caixa e remove MACs de rede em JSON, CSV e resumo — inclusive quando os detalhes vêm do snapshot básico, não só dos privilegiados.
- Resumo copiado nunca vaza MAC/identificadores mesmo se a rede tiver detalhes longos; usa dados redigidos.
- Snapshots sem `network`/`system`/`disks`/`alerts` ou programas em tuplas de 2 itens não quebram JSON/CSV/resumo.
- Exportação CSV não quebra com vírgulas/aspas/quebras de linha em nomes (usar `csv.writer`).
- Exportar JSON/CSV reutiliza a coleta privilegiada já feita (`_priv_bios/_priv_hw`) e não pede senha de novo desnecessariamente.

---

### Task 1: Resumo para suporte e helper de MAC

**Files:**
- Modify: `cleanix/xray.py`
- Modify: `cleanix/locale/{pt_BR,en,es}.json`
- Test: `tests/test_xray.py`

**Interfaces:**
- Produces: `redact_network_macs(text: str) -> str`; `build_support_summary(snapshot, bios_details='', hw_details='', bios_source='', hw_source='', priv_error='', redact=True) -> str`

- [x] **Step 1: Escrever os testes que falham**

Em `tests/test_xray.py` adicionar:
```python
class SupportSummaryTest(unittest.TestCase):
    def _snapshot(self):
        return {
            'bios': {'summary': 'BIOS: ACME 1.0', 'details': 'b',
                     'fields': {'product_name': 'PC X'}},
            'hardware': {'summary': 'CPU: X | RAM: 8 GB', 'details': 'h'},
            'programs': {'apt': [('bash','5','1 MB')], 'snap': [],
                         'flatpak_apps': [], 'flatpak_runtimes': 2,
                         'summary': 'APT: 1'},
            'network': {'summary': '1 interfaces: enp3s0',
                        'details': 'enp3s0 UP\n  IP: 10.0.0.2/24\n  MAC: aa:bb:cc:dd:ee:ff',
                        'interfaces': []},
            'system': {'summary': 'Tempo ligado: 1 h | Atualizações pendentes: 3',
                       'details': 'd', 'updates': 3},
            'disks': [{'name': 'sda', 'type': 'disk', 'size_total': 100,
                       'size_used': 50, 'pct_used': 50, 'mount_point': '/'}],
            'alerts': [{'level': 'info', 'text': '3 atualizações pendentes'}],
            'limitations': [],
        }

    def test_summary_hides_identifiers_when_redacted(self):
        text = xray.build_support_summary(
            self._snapshot(), bios_details='Serial Number: SEC-1\n', redact=True)
        self.assertNotIn('SEC-1', text)
        self.assertNotIn('aa:bb:cc:dd:ee:ff', text)
        self.assertIn('ACME', text)
        self.assertIn('enp3s0', text)

    def test_summary_keeps_identifiers_when_not_redacted(self):
        text = xray.build_support_summary(
            self._snapshot(), bios_details='Serial Number: SEC-1\n', redact=False)
        self.assertIn('SEC-1', text)
        self.assertIn('aa:bb:cc:dd:ee:ff', text)

    def test_summary_tolerates_partial_snapshot(self):
        text = xray.build_support_summary({})
        self.assertTrue(isinstance(text, str) and text)
```

- [x] **Step 2: Rodar para ver falhar**

Run: `python3 -m unittest tests.test_xray.SupportSummaryTest -v`
Expected: FAIL (funções ausentes)

- [x] **Step 3: Implementar**

Em `cleanix/xray.py`: extrair/definir `redact_network_macs(text: str) -> str` (regex `(?im)^(\s*MAC:\s*).*$` -> label + `i18n.t('xray.redacted')`) e usar no HTML. Implementar `build_support_summary(...)` montando linhas: cabeçalho com versão (`cleanix.version`/`__version__` disponível via `from . import __init__ as pkg` ou `import cleanix; cleanix.version` — usar o mesmo padrão do HTML: `cleanix_version` importado no módulo) e data/hora, SO/produto, bios/hardware summaries, discos (nome, %, montagem), rede summary + interfaces/endereços sem MAC quando redacted (ou com MAC redigido), sistema summary, contagens APT/Snap/Flatpak+runtimes, alertas (ou “nenhum”), limitações; aplicar `redact_sensitive` aos detalhes de bios/hw quando fornecidos para compor eventuais notas e sempre mascarar MACs em qualquer texto de rede incluído.

Adicionar chaves de resumo se necessário (`xray.summary.none_alerts`, `xray.summary.title` ou reaproveitar existentes) nos 3 locales.

- [x] **Step 4: Rodar testes**

Run: `python3 -m unittest tests.test_xray.SupportSummaryTest tests.test_xray.ReportHtmlV2Test -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add cleanix/xray.py cleanix/locale tests/test_xray.py
git commit -m "feat: adiciona resumo do Raio-X para suporte"
```

### Task 2: Exportação JSON

**Files:**
- Modify: `cleanix/xray.py`
- Test: `tests/test_xray.py`

**Interfaces:**
- Produces: `build_report_json(snapshot, bios_details='', hw_details='', bios_source='', hw_source='', priv_error='', redact=True) -> str`

- [x] **Step 1: Escrever os testes que falham**

```python
import json

class ReportJsonTest(unittest.TestCase):
    def _snapshot(self):
        return {
            'bios': {'summary': 'BIOS: ACME', 'details': 'b',
                     'fields': {'product_name': 'PC'}},
            'hardware': {'summary': 'CPU: T', 'details': 'h'},
            'programs': {'apt': [('bash', '5', '1 MB')], 'snap': [],
                         'flatpak_apps': [], 'flatpak_runtimes': 0,
                         'summary': 'APT: 1'},
            'network': {'summary': 'n', 'interfaces': [],
                        'details': 'enp3s0 UP\n    MAC: aa:bb:cc:dd:ee:ff'},
            'system': {'summary': 's', 'details': 'd', 'updates': 0},
            'disks': [{'name': 'sda', 'type': 'disk', 'size_total': 10,
                       'size_used': 1, 'pct_used': 10, 'mount_point': '/'}],
            'alerts': [], 'limitations': [],
        }

    def test_json_structure_and_program_size(self):
        data = json.loads(xray.build_report_json(self._snapshot()))
        self.assertIn('meta', data)
        self.assertIn('cleanix_version', data['meta'])
        self.assertEqual(data['programs']['apt'][0]['name'], 'bash')
        self.assertEqual(data['programs']['apt'][0]['size'], '1 MB')
        self.assertEqual(data['disks'][0]['name'], 'sda')

    def test_json_redacts_identifiers(self):
        data = json.loads(xray.build_report_json(
            self._snapshot(), bios_details='Serial Number: SEC\n', redact=True))
        self.assertNotIn('SEC', json.dumps(data, ensure_ascii=False))
        self.assertNotIn('aa:bb:cc:dd:ee:ff', json.dumps(data, ensure_ascii=False))
        self.assertTrue(data['meta']['redacted'])

    def test_json_keeps_identifiers_when_disabled(self):
        data = json.loads(xray.build_report_json(
            self._snapshot(), bios_details='Serial Number: SEC\n', redact=False))
        self.assertIn('SEC', data['bios']['details'])
        self.assertFalse(data['meta']['redacted'])
```

- [x] **Step 2: Rodar para ver falhar**

Run: `python3 -m unittest tests.test_xray.ReportJsonTest -v`
Expected: FAIL

- [x] **Step 3: Implementar**

Em `cleanix/xray.py`: `build_report_json` retorna `json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False)` com meta (`generated`, `cleanix_version`, `os`, `product`, `redacted`, `priv_error`), seções bios/hardware/network/system/disks/alerts/programs/limitations; programas como objetos `{name,version,size}` (tolerar tuplas de 2); aplicar redação a bios/hw details e MACs em network details quando `redact=True`.

- [x] **Step 4: Rodar testes**

Run: `python3 -m unittest tests.test_xray.ReportJsonTest -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add cleanix/xray.py tests/test_xray.py
git commit -m "feat: exporta inventário do Raio-X em JSON"
```

### Task 3: Exportação CSV

**Files:**
- Modify: `cleanix/xray.py`
- Test: `tests/test_xray.py`

**Interfaces:**
- Produces: `build_report_csv(snapshot, bios_details='', hw_details='', bios_source='', hw_source='', priv_error='', redact=True) -> str`

- [x] **Step 1: Escrever os testes que falham**

```python
import csv, io

class ReportCsvTest(unittest.TestCase):
    def _snapshot(self):
        return {
            'bios': {'summary': 'BIOS', 'details': '', 'fields': {}},
            'hardware': {'summary': '', 'details': ''},
            'programs': {
                'apt': [('bash, core', '5.2', '1 MB')],
                'snap': [('firefox', '120', '')],
                'flatpak_apps': [], 'flatpak_runtimes': 0, 'summary': ''},
            'network': {'summary': '', 'details': 'MAC: aa:bb:cc:dd:ee:ff'},
            'system': {'summary': '', 'details': ''},
            'disks': [{'name': 'sda', 'type': 'disk', 'size_total': 100,
                       'size_used': 10, 'pct_used': 10, 'mount_point': '/'}],
            'alerts': [{'level': 'warn', 'text': 'Partição / com 95% de uso'}],
            'limitations': [],
        }

    def test_csv_has_sections_and_escapes_commas(self):
        text = xray.build_report_csv(self._snapshot())
        rows = list(csv.reader(io.StringIO(text)))
        self.assertIn(['section', 'origin', 'name', 'version', 'size',
                       'type', 'total', 'used', 'pct', 'mount',
                       'level', 'text'], rows)
        program = [r for r in rows if r and r[0] == 'program' and r[1] == 'apt'][0]
        self.assertEqual(program[2], 'bash, core')
        disk = [r for r in rows if r and r[0] == 'disk'][0]
        self.assertEqual(disk[2], 'sda')
        alert = [r for r in rows if r and r[0] == 'alert'][0]
        self.assertEqual(alert[10], 'warn')

    def test_csv_redacts_mac_when_enabled(self):
        text = xray.build_report_csv(
            self._snapshot(), bios_details='Serial Number: SEC\n', redact=True)
        self.assertNotIn('aa:bb:cc:dd:ee:ff', text)
        self.assertNotIn('SEC', text)
```

- [x] **Step 2: Rodar para ver falhar**

Run: `python3 -m unittest tests.test_xray.ReportCsvTest -v`
Expected: FAIL

- [x] **Step 3: Implementar**

Em `cleanix/xray.py`: `build_report_csv` gera via `csv.writer` em `io.StringIO` com cabeçalho fixo `section,origin,name,version,size,type,total,used,pct,mount,level,text`. Linhas: `program` para cada item de apt/snap/flatpak_apps (origin `apt|snap|flatpak`); `disk` para cada disco (campos total/used como bytes ou texto legível — usar `systeminfo.format_bytes` quando houver valor, para consistência com HTML); `alert` para cada destaque. Não incluir detalhes brutos de BIOS/hardware/rede com identificadores; se precisar incluir nota de privacidade, usar seção `meta` apenas com campos seguros (sem MAC/serial). Aplicar redação a qualquer texto derivado de bios/hw/network incluído.

- [x] **Step 4: Rodar testes**

Run: `python3 -m unittest tests.test_xray.ReportCsvTest -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add cleanix/xray.py tests/test_xray.py
git commit -m "feat: exporta inventário do Raio-X em CSV"
```

### Task 4: Diálogo, i18n e integração da exportação

**Files:**
- Modify: `cleanix/dialogs.py`
- Modify: `cleanix/locale/{pt_BR,en,es}.json`
- Modify: `README.md` (seção Raio-X: mencionar JSON/CSV/resumo)
- Test: `tests/test_xray.py` (já coberto) + smoke manual/GTK simples se útil

**Interfaces:**
- Consumes: `xray.build_report_json`, `xray.build_report_csv`, `xray.build_support_summary`
- Produces: UI com “Copiar resumo”, “Exportar JSON”, “Exportar CSV”; exportação generalizada respeitando `redact_check`.

- [x] **Step 1: Adicionar chaves i18n**

Nos 3 arquivos de locale adicionar (valores equivalentes): `xray.copy_summary` (Copiar resumo), `xray.summary_copied` (Resumo copiado.), `xray.export_json` (Exportar JSON), `xray.export_csv` (Exportar CSV), `xray.export_json_title`, `xray.export_csv_title`, `xray.export_json_filename` (`cleanix-raiox.json` base — nome final pode incluir data, mas manter chave), `xray.export_csv_filename`, `xray.export_json_done_body`/`csv` ou reutilizar mensagens genéricas. Manter paridade de chaves.

- [x] **Step 2: Implementar UI e exportação no diálogo**

Em `XRayDialog`: adicionar botão “Copiar resumo” (`_make_copy_button`/ação dedicada) que chama `xray.build_support_summary(...)` com textos atuais e `redact=self.redact_check.get_active()` e copia para clipboard com status “Resumo copiado.”. Adicionar botões “Exportar JSON” e “Exportar CSV”. Refatorar exportação para aceitar `kind in ('html','json','csv')`: nomes/títulos/geradores por tipo; JSON/CSV usam `self._open_report` apenas se fizer sentido (pode abrir pasta não é trivial com FileDialog — manter comportamento de mostrar caminho no diálogo de sucesso, sem abrir navegador; HTML continua abrindo). Reutilizar `_write_export/_export_work/_finish_export` garantindo que coleta privilegiada ocorra uma vez quando necessário e que `redact_check` seja passado aos builders.

- [x] **Step 3: Atualizar README**

Acrescentar na descrição do Raio-X/relatório que também é possível exportar JSON e CSV e copiar um resumo para suporte, sempre respeitando a ocultação de identificadores.

- [x] **Step 4: Verificação**

Run: `python3 -m unittest discover -s tests -v` (todos OK)
Run: `python3 tools/check_language.py` (OK)
Run: `python3 tools/check_layout.py` (OK)
Smoke rápido opcional: instanciar builders com snapshot real (`xray.collect_unprivileged()`) e conferir que JSON/CSV/summary geram e não contêm MAC/serial quando `redact=True`.

- [x] **Step 5: Commit**

```bash
git add cleanix/dialogs.py cleanix/locale README.md
git commit -m "feat: adiciona exportação JSON/CSV e resumo para suporte no Raio-X"
```

### Task 5: Fechamento do lote 1

- [x] **Step 1:** `python3 -m unittest discover -s tests -v` — esperado: todos OK.
- [x] **Step 2:** Atualizar `docs/superpowers/plans/2026-11-16-cleanix-xray-lote1.md` marcando passos concluídos.
- [x] **Step 3:** Commit `docs: registra conclusão do lote 1 do Raio-X` e `git push origin feat/funcionalidades-reais`.
