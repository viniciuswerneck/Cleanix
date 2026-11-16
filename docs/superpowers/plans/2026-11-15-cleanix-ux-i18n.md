# Cleanix — reorganização da interface e três idiomas: plano

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganizar menus/painéis da tela inicial (caminho A) e traduzir todo o app para pt-BR, en e es com troca imediata em Configurações.

**Architecture:** Uma camada `i18n` lê catálogos JSON planos e expõe `t`/`tn`/formatação. A UI passa a pedir todo texto a essa camada. A janela principal é reconstruída ao trocar o idioma, preservando dados já escaneados. Nenhuma lógica de limpeza muda.

**Tech Stack:** Python 3.10+, GTK4/PyGObject, Cairo, `unittest`, JSON.

**Spec:** `docs/superpowers/specs/2026-11-15-cleanix-ux-i18n-design.md`

## Global Constraints

- Sem dependência nova; apenas stdlib + GTK4/PyGObject já usados.
- O app roda direto do código: nada de etapa de build para traduções.
- Nenhuma mudança na allowlist, varredura, remoção ou comandos administrativos.
- `format_bytes`, `format_timestamp` e assinaturas públicas existentes continuam válidas.
- Os três catálogos têm exatamente o mesmo conjunto de chaves.
- Testes que verificam texto forçam `i18n.set_language('pt_BR')`.
- Idioma padrão `pt_BR` quando não há preferência nem detecção.
- Tela de 1366×768: rótulos primários curtos, com `wrap` onde já existe.
- Comentários e nomes internos podem ficar em português; logs não são traduzidos.

## Review Focus

1. **Trocar de idioma duas vezes seguidas, com varredura/timer rodando** — a UI deve continuar viva, sem referência a widget destruído.
2. **Chave faltando em um catálogo** — o app não pode mostrar `sidebar.home`; deve cair em pt-BR e o teste de paridade/AST deve acusar.
3. **Idioma inválido no `config.json`** — o app abre em pt-BR (ou no idioma detectado), sem traceback.
4. **Textos longos em en/es na largura de 1366** — botões primários não podem ser cortados; rótulos primários ficam curtos.
5. **`gsettings` indisponível** — Ajustes abre com switches desabilitados e uma mensagem, sem fechar nem travar.

Cada linha acima ganha teste na tarefa que possui o código (Tasks 1, 2, 6, 8, 9, 10).

---

### Task 1: Camada de idiomas e catálogos

**Files:**
- Create: `cleanix/i18n.py`
- Create: `cleanix/locale/pt_BR.json`, `cleanix/locale/en.json`, `cleanix/locale/es.json`
- Test: `tests/test_i18n.py`

**Interfaces:**
- Produces:
  - `LANGUAGES: tuple[str, ...] = ('pt_BR', 'en', 'es')`
  - `LANGUAGE_NAMES: dict[str, str]` (`Português`, `English`, `Español`)
  - `detect_language(env: Mapping[str, str] | None = None) -> str`
  - `set_language(code: str) -> bool`
  - `get_language() -> str`
  - `t(key: str, **values) -> str`
  - `tn(key: str, n: int, **values) -> str`
  - `format_number(value: float, decimals: int = 0) -> str`
  - `format_datetime(iso: str) -> str`
  - `catalog_keys(code: str) -> set[str]`

- [ ] **Step 1: Escrever os testes**

`tests/test_i18n.py` deve conter, no mínimo:

```python
class CatalogTest(unittest.TestCase):
    def test_three_catalogs_have_same_keys(self):
        base = i18n.catalog_keys('pt_BR')
        self.assertTrue(base)
        for code in i18n.LANGUAGES:
            self.assertEqual(i18n.catalog_keys(code), base, code)

    def test_missing_key_returns_key_and_logs(self):
        i18n.set_language('en')
        self.assertEqual(i18n.t('chave.inexistente'), 'chave.inexistente')

class PluralTest(unittest.TestCase):
    def test_one_and_other(self):
        i18n.set_language('pt_BR')
        self.assertEqual(i18n.tn('files.removed', 1), '1 arquivo removido')
        self.assertEqual(i18n.tn('files.removed', 3), '3 arquivos removidos')

class NumberTest(unittest.TestCase):
    def test_locale_separators(self):
        i18n.set_language('pt_BR')
        self.assertEqual(i18n.format_number(1234.5, 1), '1.234,5')
        i18n.set_language('en')
        self.assertEqual(i18n.format_number(1234.5, 1), '1,234.5')
        i18n.set_language('es')
        self.assertEqual(i18n.format_number(1234.5, 1), '1.234,5')

class DateTimeTest(unittest.TestCase):
    def test_date_order(self):
        i18n.set_language('en')
        self.assertEqual(i18n.format_datetime('2026-11-15T10:20:00'),
                         '11/15/2026 10:20')
        i18n.set_language('pt_BR')
        self.assertEqual(i18n.format_datetime('2026-11-15T10:20:00'),
                         '15/11/2026 10:20')

class DetectTest(unittest.TestCase):
    def test_env_prefixes(self):
        self.assertEqual(i18n.detect_language({'LANG': 'pt_BR.UTF-8'}), 'pt_BR')
        self.assertEqual(i18n.detect_language({'LANG': 'en_US.UTF-8'}), 'en')
        self.assertEqual(i18n.detect_language({'LANG': 'es_ES.UTF-8'}), 'es')
        self.assertEqual(i18n.detect_language({'LANG': 'fr_FR.UTF-8'}), 'pt_BR')

class AstKeysTest(unittest.TestCase):
    def test_literal_keys_used_in_code_exist(self):
        # varre cleanix/*.py com ast e confere t('...') e tn('...'),
        # incluindo .one/.other para tn.
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python3 -m unittest tests.test_i18n -v`
Expected: FAIL/ERROR porque `cleanix.i18n` não existe.

- [ ] **Step 3: Implementar**

`i18n.py`:
- `_catalogs: dict[str, dict[str, str]]` carregado sob demanda de
  `Path(__file__).with_name('locale') / f'{code}.json'`; cachear.
- `_current = 'pt_BR'`.
- `set_language` aceita só `LANGUAGES`; inválido vira `pt_BR` e retorna `False`.
- `t`: catálogo atual → `pt_BR` → a própria chave; loga `warning` quando faltar.
- `tn`: usa `f'{key}.one'` se `n == 1` senão `f'{key}.other'`, injeta `n`.
- `format_number`: formata com `f'{value:,.{decimals}f}'`; em pt/es troca
  vírgula↔ponto via placeholder; em en mantém.
- `format_datetime`: `datetime.fromisoformat(iso).strftime(t('date.pattern'))`;
  em erro devolve `iso`.

Catálogos iniciais (mesmas chaves nos três):
`app.name`, `app.subtitle`, `common.close`, `common.cancel`,
`date.pattern`, `files.removed.one`, `files.removed.other`.

Traduções: pt-BR `{n} arquivo removido` / `{n} arquivos removidos`;
en `{n} file removed` / `{n} files removed`; es `{n} archivo eliminado` /
`{n} archivos eliminados`.

- [ ] **Step 4: Rodar e ver passar**

Run: `python3 -m unittest tests.test_i18n -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cleanix/i18n.py cleanix/locale tests/test_i18n.py
git commit -m "feat(i18n): catalogs and translation layer for pt-BR, en and es"
```

---

### Task 2: Preferência de idioma e abertura do app

**Files:**
- Modify: `cleanix/settings.py`
- Modify: `cleanix/main.py`
- Test: `tests/test_settings.py`

**Interfaces:**
- Consumes: `i18n.LANGUAGES`, `i18n.detect_language`, `i18n.set_language`.
- Produces: `Settings.language: str` (padrão `''`).

- [ ] **Step 1: Testes**

Adicionar a `tests/test_settings.py`:

```python
def test_language_round_trip(self):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.json"
        original = settings.Settings(language="en")
        settings.save_settings(original, path)
        self.assertEqual(settings.load_settings(path).language, "en")

def test_invalid_language_falls_back_to_auto(self):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.json"
        path.write_text(json.dumps({"language": "fr"}), encoding="utf-8")
        self.assertEqual(settings.load_settings(path).language, "")

def test_non_string_language_falls_back(self):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.json"
        path.write_text(json.dumps({"language": 3}), encoding="utf-8")
        self.assertEqual(settings.load_settings(path).language, "")
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python3 -m unittest tests.test_settings -v`
Expected: FAIL (`Settings` sem `language`).

- [ ] **Step 3: Implementar**

- `Settings`: `language: str = ""`.
- `load_settings`: respeitar `bool` e `str`; para `language`, aceitar apenas
  `""` ou código em `i18n.LANGUAGES`; o resto vira `""`.
- `main.py`: depois do logging e antes de criar a janela:

```python
from . import i18n, settings
cfg = settings.load_settings()
i18n.set_language(cfg.language or i18n.detect_language())
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python3 -m unittest tests.test_settings -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cleanix/settings.py cleanix/main.py tests/test_settings.py
git commit -m "feat(settings): persist and apply the interface language"
```

---

### Task 3: Números e distribuição por idioma

**Files:**
- Modify: `cleanix/systeminfo.py`
- Test: `tests/test_systeminfo.py`

**Interfaces:**
- Consumes: `i18n.format_number`.
- Produces: `distro_name(path: str = '/etc/os-release') -> str`.

- [ ] **Step 1: Testes**

```python
class LocalizedBytesTest(unittest.TestCase):
    def tearDown(self):
        i18n.set_language('pt_BR')

    def test_english_uses_dot(self):
        i18n.set_language('en')
        self.assertEqual(si.format_bytes(1024), '1.00 KB')
        self.assertEqual(si.format_bytes(int(78.4 * 1024**3)), '78.4 GB')

    def test_spanish_uses_comma(self):
        i18n.set_language('es')
        self.assertEqual(si.format_bytes(1024), '1,00 KB')

class DistroNameTest(unittest.TestCase):
    def test_prefers_pretty_name(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'os-release'
            p.write_text('NAME="Ubuntu"\nVERSION_ID="26.04"\n'
                         'PRETTY_NAME="Ubuntu 26.04.1 LTS"\n', encoding='utf-8')
            self.assertEqual(si.distro_name(str(p)), 'Ubuntu 26.04.1 LTS')

    def test_falls_back_to_name_and_version(self):
        ...
        self.assertEqual(si.distro_name(str(p)), 'Ubuntu 26.04')

    def test_missing_file_returns_linux(self):
        self.assertEqual(si.distro_name('/nao/existe'), 'Linux')
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python3 -m unittest tests.test_systeminfo -v`
Expected: FAIL nos novos testes.

- [ ] **Step 3: Implementar**

- Substituir `_format_number` por delegação a `i18n.format_number` (manter
  `format_percent`).
- `format_bytes` igual, mas usando o formatador localizado.
- `distro_name`: ler pares `CHAVE="valor"`; preferir `PRETTY_NAME`; senão
  `NAME` + `VERSION_ID`; erro → `"Linux"`.
- Garantir que os testes antigos continuam verdes porque o padrão é `pt_BR`.

- [ ] **Step 4: Rodar e ver passar**

Run: `python3 -m unittest tests.test_systeminfo tests.test_scanner -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cleanix/systeminfo.py tests/test_systeminfo.py
git commit -m "feat(systeminfo): localize number formatting and read the real distro"
```

---

### Task 4: Data do histórico por idioma

**Files:**
- Modify: `cleanix/history.py`
- Test: `tests/test_history.py`

**Interfaces:**
- Consumes: `i18n.format_datetime`.

- [ ] **Step 1: Teste**

Adicionar:

```python
def test_format_timestamp_english(self):
    i18n.set_language('en')
    try:
        self.assertEqual(history.format_timestamp('2026-11-15T10:20:00'),
                         '11/15/2026 10:20')
    finally:
        i18n.set_language('pt_BR')
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python3 -m unittest tests.test_history -v`
Expected: FAIL.

- [ ] **Step 3: Implementar**

`format_timestamp` delega para `i18n.format_datetime`; comportamento de erro
devolve a string original.

- [ ] **Step 4: Rodar e ver passar**

Run: `python3 -m unittest tests.test_history -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cleanix/history.py tests/test_history.py
git commit -m "feat(history): localize cleaning timestamps"
```

---

### Task 5: Menu lateral, rodapé e Ajuda/Sobre

**Files:**
- Modify: `cleanix/cleanixwindow.py`
- Modify: `cleanix/dialogs.py`
- Modify: `cleanix/locale/*.json`
- Test: `tests/test_dialogs.py`

**Interfaces:**
- Consumes: `i18n.t`, `systeminfo.distro_name`.
- Produces: `dialogs.help_about_text() -> tuple[str, str]` (título, corpo).

- [ ] **Step 1: Teste**

Adicionar a `tests/test_dialogs.py`:

```python
class HelpAboutTextTest(unittest.TestCase):
    def tearDown(self):
        i18n.set_language('pt_BR')

    def test_portuguese_has_safety_and_version(self):
        i18n.set_language('pt_BR')
        title, body = dialogs.help_about_text()
        self.assertEqual(title, 'Ajuda e Sobre')
        self.assertIn('Cleanix 1.0', body)
        self.assertIn('/tmp', body)

    def test_english(self):
        i18n.set_language('en')
        title, _ = dialogs.help_about_text()
        self.assertEqual(title, 'Help & About')
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python3 -m unittest tests.test_dialogs.HelpAboutTextTest -v`
Expected: FAIL.

- [ ] **Step 3: Implementar**

`dialogs.py`:
- `help_about_text()` monta título (`help.title`) e corpo com
  `help.body`, `about.version` (`Cleanix 1.0`) e
  `about.distro` (`{name}`).
- Chaves novas nos três catálogos.

`cleanixwindow.py`:
- Menu: `sidebar.home`, `sidebar.cleanup`, `sidebar.optimize`,
  `sidebar.adjustments`, `sidebar.history`, `sidebar.help_about`.
  Remover os subtítulos em inglês.
- “Ajuda e Sobre” chama `_show_help_about`; remover `_show_about`.
- Rodapé: um único rótulo com `systeminfo.distro_name()`; remover
  “22.04 LTS” fixo.
- Barra inferior: remover o botão “Ajuda”; manter “Configurações”.
- `_show_help` vira `_show_help_about` usando `help_about_text()`.

- [ ] **Step 4: Rodar e ver passar**

Run: `python3 -m unittest tests.test_dialogs -v`
Expected: PASS (os testes antigos de actions ainda passam até a Task 7).

- [ ] **Step 5: Commit**

```bash
git add cleanix/cleanixwindow.py cleanix/dialogs.py cleanix/locale tests/test_dialogs.py
git commit -m "feat(ui): Portuguese-only menu, real distro footer and merged help/about"
```

---

### Task 6: Reorganizar a tela inicial

**Files:**
- Modify: `cleanix/cleanixwindow.py`
- Modify: `cleanix/styles.css` (só se necessário)
- Modify: `cleanix/locale/*.json`
- Test: `tools/check_layout.py` (novo harness de verificação)

**Interfaces:**
- Consumes: `t`, `tn`, `format_bytes`.
- Produces: widgets `cleanup_review_btn`, `cat_rows: dict[str, Gtk.Label]`,
  `cpu_now_label`.

- [ ] **Step 1: Escrever o harness de layout**

`tools/check_layout.py` cria a janela, espera a varredura e imprime/verifica:
- títulos na ordem: Saúde, Limpeza, Memória RAM, Uso do Disco, Uso de CPU,
  Últimas Ações;
- não existe rótulo “O que deseja fazer?”;
- o cartão de limpeza usa o botão “Revisar e limpar”;
- a lista de categorias da tela inicial não contém `Gtk.CheckButton`;
- o cartão de CPU tem título “Uso de CPU” e o texto “agora”.

Sai com código 1 e lista de falhas quando algo não bate.

- [ ] **Step 2: Rodar e ver falhar**

Run: `timeout 60 python3 tools/check_layout.py`
Expected: FAIL (estrutura atual ainda tem “O que deseja fazer?” etc.).

- [ ] **Step 3: Implementar**

- `_content`: Saúde → Limpeza → RAM → Disco/CPU → Últimas Ações.
- `_block_cleanup`: “Espaço Recuperável”, botão “Revisar e limpar”, lista
  somente leitura (`category.{key}`, tamanho) e a rosca de categorias.
  Checkboxes saem; `cat_rows[key] = size_label`.
- `_block_memory`: usa `self._memory_values` ao criar o gráfico.
- `_block_disk_cpu`: rosca do disco + cartão “Uso de CPU” com
  `cpu_now_label` (`cpu.now` = `{pct}% agora`) e `metric.cores`
  (`{n} núcleo(s)`).
- Remover `_block_cards`, `_block_actions`, `_action`, `_on_cat_toggle`,
  `_sync_checks`, `action_buttons` e o conector `close-request` de
  `_open_details`.
- `_refresh_categories`: só atualiza tamanhos (ou “—”), sem checkbox.
- `_refresh_system`: atualiza `cpu_now_label` e mantém o resto.
- `_tick_cpu`: atualiza o gráfico e `cpu_now_label`.
- Traduzir todos os textos desta tela com chaves novas nos três catálogos.
- `HEALTH_TEXTS` passa a guardar chaves de tradução em vez de texto.

- [ ] **Step 4: Rodar e ver passar**

Run: `timeout 60 python3 tools/check_layout.py`
Expected: PASS.
Run: `python3 tools/screenshot.py --out /tmp/opencode/cleanix_layout.png`
Expected: painéis na ordem nova; conferir visualmente.

- [ ] **Step 5: Commit**

```bash
git add cleanix/cleanixwindow.py cleanix/styles.css cleanix/locale tools/check_layout.py
git commit -m "feat(dashboard): put cleaning first and remove duplicated panels"
```

---

### Task 7: Traduzir diálogos e renomear ações

**Files:**
- Modify: `cleanix/dialogs.py`
- Modify: `cleanix/locale/*.json`
- Test: `tests/test_dialogs.py`

**Interfaces:**
- Produces: cada ação do Otimizador usa `label_key`, `description_key`,
  `detail_key` (em vez de textos fixos).

- [ ] **Step 1: Testes**

Atualizar `tests/test_dialogs.py`:
- `setUp` chama `i18n.set_language('pt_BR')`.
- `ActionListsTest` procura `label_key` e confere:
  `t('optimizer.apt.label') == 'Limpar cache do APT'`,
  `t('optimizer.journal.label') == 'Limpar logs antigos'`,
  `t('optimizer.fstrim.label') == 'Otimizar SSD'`,
  `t('optimizer.startup.label') == 'Aplicativos de inicialização'`,
  `t('optimizer.memory.label') == 'Memória RAM'`.
- Novo teste: para cada ação, `label_key`, `description_key` e `detail_key`
  existem nos três catálogos.
- Manter `test_optimizer_commands_need_root` etc.

- [ ] **Step 2: Rodar e ver falhar**

Run: `python3 -m unittest tests.test_dialogs -v`
Expected: FAIL.

- [ ] **Step 3: Implementar**

- `_ActionDialog._action_row`/`_on_clicked`/`_start`/`_done` usam
  `t(action['label_key'])`; `_buttons` indexado por `label_key`.
- `OPTIMIZER_ACTIONS` só com chaves e campos técnicos.
- `DetailsDialog`: título, subtítulo, “Total selecionado”, “Cancelar”,
  “Limpar agora”, estados e tooltip via `t`/`tn`.
- `MemoryDialog`, `HistoryDialog` e `StartupAppsDialog`: todos os textos via
  `t`/`tn`.
- `confirm(...)`: botão “Cancelar” via `common.cancel`.
- Remover `_plural` e usar `tn('files...', n)`.
- Adicionar as chaves usadas aos três catálogos (não deixar string em
  português fora dos catálogos).
- Manter comandos e chaves internas intactos.

- [ ] **Step 4: Rodar e ver passar**

Run: `python3 -m unittest tests.test_dialogs -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cleanix/dialogs.py cleanix/locale tests/test_dialogs.py
git commit -m "feat(dialogs): translate every dialog and use plain-language actions"
```

---

### Task 8: Ajustes com switches reais

**Files:**
- Create: `cleanix/adjustments.py`
- Modify: `cleanix/dialogs.py`
- Modify: `cleanix/locale/*.json`
- Test: `tests/test_adjustments.py`

**Interfaces:**
- Produces:
  - `parse_gsettings_bool(text: str) -> bool | None`
  - `get_animations() -> bool | None`
  - `set_animations(enabled: bool) -> Result`
  - `get_privacy_cleanup() -> bool | None`
  - `set_privacy_cleanup(enabled: bool) -> Result`

- [ ] **Step 1: Testes**

`tests/test_adjustments.py`:
- `parse_gsettings_bool('true\n') is True`, `'false'` False, lixo → None.
- `get_animations` executa `gsettings get org.gnome.desktop.interface
  enable-animations` e converte.
- `set_animations(False)` executa `gsettings set ... false`.
- `set_privacy_cleanup(True)` executa os dois `gsettings set` ligados por
  `&&`.
- Falha do comando devolve `None`/`Result(False, ...)` sem exceção.

- [ ] **Step 2: Rodar e ver falhar**

Run: `python3 -m unittest tests.test_adjustments -v`
Expected: ERROR (módulo não existe).

- [ ] **Step 3: Implementar**

- `adjustments.py` com `execute_command` (sem root) e as funções acima.
- `AdjustmentsDialog` vira diálogo com dois switches:
  - “Animações do sistema” (chave `adjust.animations.*`);
  - “Limpar lixeira e temporários antigos automaticamente”
    (`adjust.privacy.*`).
  - Estado inicial lido com `get_*`; `_restoring` evita sinal durante o ajuste.
  - Falha: switch volta ao estado anterior e o status mostra
    `adjust.error` (`{detail}`).
- Remover `ADJUSTMENT_ACTIONS` e atualizar `tests/test_dialogs.py`
  (remover o teste antigo de adjustments).
- Chaves novas nos três catálogos.

- [ ] **Step 4: Rodar e ver passar**

Run: `python3 -m unittest tests.test_adjustments tests.test_dialogs -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cleanix/adjustments.py cleanix/dialogs.py cleanix/locale tests/test_adjustments.py tests/test_dialogs.py
git commit -m "feat(adjustments): replace opposite actions with real switches"
```

---

### Task 9: Seletor de idioma e reconstrução da janela

**Files:**
- Modify: `cleanix/dialogs.py`
- Modify: `cleanix/cleanixwindow.py`
- Modify: `cleanix/locale/*.json`
- Test: `tools/check_language.py` (novo harness)

**Interfaces:**
- `SettingsDialog(parent, on_language_changed=None)`.
- `CleanixWindow._apply_language(code: str) -> None`.

- [ ] **Step 1: Escrever o harness**

`tools/check_language.py`:
- abre a janela, espera a varredura;
- troca para `en`, chama `_apply_language('en')` e confere
  “Cleanup”, “Optimization”, “Adjustments”, “Help & About”;
- troca para `es` e confere “Limpieza”, “Optimización”, “Ajustes”,
  “Ayuda y Acerca de”;
- volta para `pt_BR` e confere “Limpeza”, “Otimização”, “Ajustes”,
  “Ajuda e Sobre”;
- confere que o gráfico de RAM continua ganhando amostras depois da troca;
- falha com código 1 se algo não bater.

- [ ] **Step 2: Rodar e ver falhar**

Run: `timeout 60 python3 tools/check_language.py`
Expected: FAIL (`_apply_language` não existe).

- [ ] **Step 3: Implementar**

- `SettingsDialog` ganha `Gtk.DropDown` com `LANGUAGE_NAMES` na ordem de
  `LANGUAGES`; seleção inicial = idioma atual; `_recording` evita salvar
  durante a montagem.
- Ao mudar: monta `Settings` com os switches atuais + `language`, salva,
  chama `on_language_changed(code)` e fecha.
- `CleanixWindow._show_settings` passa `on_language_changed=self._apply_language`.
- `_apply_language`:
  - `if not i18n.set_language(code): return`
  - limpa `cat_rows`, `metric_labels`, `metric_bars`, `history_rows`
  - reconstrói com `_build_ui()`
  - repinta com `_refresh_system()`, `_refresh_recoverable()`,
    `_refresh_categories()`, `_refresh_history()`
  - preserva `results`, `selected`, `_line_values` e `_memory_values`.
- `_block_memory`/`_block_disk_cpu` devem semear os gráficos com as listas
  preservadas.
- Chaves de Configurações/idioma nos três catálogos.
- Cobrir o caso “idioma inválido no `config.json`” já garantido na Task 2;
  adicionar ao harness uma troca `_apply_language('fr')` que mantém o idioma
  atual sem exceção.

- [ ] **Step 4: Rodar e ver passar**

Run: `timeout 60 python3 tools/check_language.py`
Expected: PASS.
Run: `python3 -m unittest discover -s tests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cleanix/dialogs.py cleanix/cleanixwindow.py cleanix/locale tools/check_language.py
git commit -m "feat(settings): switch language immediately and rebuild the main window"
```

---

### Task 10: Documentação e verificação final

**Files:**
- Modify: `README.md`
- Modify: `implementation-status.md`

- [ ] **Step 1: Atualizar a documentação**

README:
- recursos: menu em português, ação principal no topo, painel de CPU rotulado,
  três idiomas;
- estrutura: `i18n.py`, `locale/`, `adjustments.py`;
- seção “Idiomas”: detecção, seletor, catálogos JSON, como adicionar textos.

implementation-status:
- menu/painéis novos;
- i18n e formatação por idioma;
- remover pendências que deixaram de existir.

- [ ] **Step 2: Verificação completa**

Run:
```bash
python3 -m unittest discover -s tests -v
timeout 60 python3 tools/check_layout.py
timeout 60 python3 tools/check_language.py
python3 tools/screenshot.py --out /tmp/opencode/cleanix_final_pt.png
LANG=en_US.UTF-8 python3 tools/screenshot.py --out /tmp/opencode/cleanix_final_en.png
LANG=es_ES.UTF-8 python3 tools/screenshot.py --out /tmp/opencode/cleanix_final_es.png
```

Expected: todos PASS; três capturas conferidas visualmente (sem corte de
botões, painéis na ordem nova).

- [ ] **Step 3: Commit**

```bash
git add README.md implementation-status.md
git commit -m "docs: document the new navigation and three languages"
```
