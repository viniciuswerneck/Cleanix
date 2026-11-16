# Melhorias do Raio-X — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:executing-plans (native) or superpowers:subagent-driven-development. Steps use checkbox (`- [x]`) syntax.

**Goal:** Tornar o Raio-X e seu relatório HTML mais seguros, completos, traduzidos e úteis, incluindo privacidade de identificadores, tamanhos de programas, rede, sistema, discos, alertas e ações no relatório.

**Architecture:** A coleta continua em `cleanix/xray.py` (thread, sem privilégios, com uma senha única na exportação). A montagem do HTML vira uma função pura e testável. O diálogo em `cleanix/dialogs.py` apenas orquestra coleta, cartões e exportação. Textos novos entram nos três catálogos i18n.

**Tech Stack:** Python 3, GTK4 (`gi`), HTML/CSS/JS autocontido, `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-16-cleanix-xray-improvements-design.md`

## Global Constraints
- Nunca instalar dependências automaticamente; a senha só aparece via `pkexec` na exportação/“Detalhes completos”.
- Todo conteúdo do sistema deve ser escapado no HTML (`html.escape`).
- Manter pt-BR, inglês e espanhol com as mesmas chaves.
- Nada de rede; `apt list --upgradable` lê apenas o cache local.
- Não alterar o fluxo de saúde SMART dos discos.

## Review Focus
- `Serial Number`, `UUID`, `SKU Number`, `Asset Tag` e `serial:` presentes em saídas reais de `dmidecode`/`lshw` devem sumir do HTML quando a privacidade estiver ativa — testar variações de caixa e espaços.
- Saídas de `ip` e `flatpak` variam por versão/locale; parsers devem ignorar linhas inesperadas sem exceção.
- Nomes de pacotes maliciosos (`<script>`) continuam escapados com as novas colunas.
- Programa sem tamanho (Snap) não pode aparecer como `None`/`()`, e sim vazio.
- Listas grandes (2.700+ APT) não podem travar a interface: renderização limitada a 500 até o usuário pedir “Mostrar todos”.

---

### Task 1: i18n dos detalhes e mascaramento de identificadores

**Files:**
- Modify: `cleanix/xray.py` (`_bios_details`, `_hardware_details`, `collect_privileged_*`)
- Modify: `cleanix/locale/{pt_BR,en,es}.json`
- Test: `tests/test_xray.py`

**Interfaces:**
- Produces: `redact_sensitive(text: str) -> str`; `xray.field.*`/`xray.section.*` keys.

- [x] **Step 1: Escrever testes que falham**

```python
def test_redact_sensitive_masks_identifiers():
    text = ("Serial Number: ABC123\nUUID: 1234\nSKU Number: X\n"
            "Asset Tag: T\n  serial: 99\n")
    out = xray.redact_sensitive(text)
    self.assertNotIn('ABC123', out)
    self.assertNotIn('1234', out)
    self.assertIn('[oculto]', out)

def test_bios_details_follow_language():
    i18n.set_language('en')
    try:
        text = xray._bios_details({'bios_vendor': 'ACME', 'bios_version': '1.0'})
    finally:
        i18n.set_language('pt_BR')
    self.assertIn('Vendor', text)
```

- [x] **Step 2: Rodar e ver falhar** — `python3 -m unittest tests.test_xray -v`
- [x] **Step 3: Implementar** — adicionar `i18n` nas mensagens; chaves `xray.section.*`, `xray.field.*`, `xray.error.*`; `redact_sensitive` com regex por linha (`serial number|uuid|sku|asset tag|^\s*serial\s*:`), preservando o rótulo e trocando o valor por `[oculto]`.
- [x] **Step 4: Rodar** — testes passam; `tools/check_language.py` OK.
- [x] **Step 5: Commit** — `feat: traduz detalhes do Raio-X e mascara identificadores`.

### Task 2: Programas com tamanho

**Files:**
- Modify: `cleanix/xray.py` (`parse_dpkg_query`, `parse_snap_list`, `parse_flatpak_list`, `collect_unprivileged`)
- Modify: `cleanix/dialogs.py` (`_update_prog_list`)
- Test: `tests/test_xray.py`

**Interfaces:**
- Produces: listas `[(nome, versão, tamanho)]`; `xray.format_kb(kb: int) -> str`.

- [x] **Step 1: Testes** — dpkg com 4ª coluna `Installed-Size` vira tamanho legível; snap devolve terceiro item `''`; flatpak lê `size`.
- [x] **Step 2: Rodar e ver falhar.**
- [x] **Step 3: Implementar** — `dpkg-query -f '${Package}\t${Version}\t${db:Status-Status}\t${Installed-Size}\n'`; `flatpak list --app --columns=application,version,size`; normalizar tamanhos ausentes para `''`.
- [x] **Step 4: Ajustar diálogo e HTML** — exibir `nome — versão · tamanho`; coluna “Tamanho” no relatório; entradas antigas de 2 itens continuam aceitas.
- [x] **Step 5: Testes + commit** — `feat: mostra tamanho dos programas no Raio-X`.

### Task 3: Coletas novas (rede, sistema, discos, destaques)

**Files:**
- Modify: `cleanix/xray.py`
- Test: `tests/test_xray.py`

**Interfaces:**
- Produces:
  - `parse_ip_brief(text) -> list[dict]` (interface, state, addresses)
  - `collect_network() -> {'summary', 'details', 'interfaces'}` (MAC incluso)
  - `collect_system() -> {'summary', 'details', 'uptime', 'updates', 'secure_boot', 'tpm'}`
  - `build_alerts(bios_date, disk_usages, flatpak_runtimes, pending_updates, now_year) -> list[dict]` com `level` (`warn`/`info`) e `text`
  - `collect_unprivileged()` passa a devolver `network`, `system`, `disks`, `alerts`.

- [x] **Step 1: Testes** — parser de `ip -brief addr`, parser de uptime, alertas determinísticos (BIOS 2015 → warn; disco 95% → warn; 22 runtimes → info; 0 updates → sem alerta).
- [x] **Step 2: Rodar e ver falhar.**
- [x] **Step 3: Implementar** — `/proc/uptime`, `/sys/class/net/*/address`, `ip -brief addr` (timeout curto), `apt list --upgradable` (timeout 20), Secure Boot em `/sys/firmware/efi/efivars/SecureBoot-*`, TPM em `/sys/class/tpm/tpm0`; discos via `systeminfo._scan_disks()`.
- [x] **Step 4: Rodar** — testes e harness de layout OK.
- [x] **Step 5: Commit** — `feat: adiciona rede, sistema, discos e destaques ao Raio-X`.

### Task 4: Relatório HTML v2

**Files:**
- Modify: `cleanix/xray.py` (`build_report_html`)
- Test: `tests/test_xray.py`

**Interfaces:**
- Consumes: snapshot com `network`, `system`, `disks`, `alerts`; `redact_sensitive`.
- Produces: `build_report_html(snapshot, bios_details='', hw_details='', bios_source='', hw_source='', priv_error='', redact=True)`.

- [x] **Step 1: Testes** — HTML contém seções Rede/Sistema/Discos, cartão Destaques, botões Imprimir/Tema/Topo, versão do Cleanix; `redact=True` remove serial; `redact=False` mantém.
- [x] **Step 2: Rodar e ver falhar.**
- [x] **Step 3: Implementar** — tabela de discos, cartões novos, TOC ampliado, CSS escuro por `[data-theme="dark"]`, botões e JS (print, tema, topo, ordenação de tabelas e busca existente), rodapé com `cleanix.version`.
- [x] **Step 4: Gerar relatório e conferir no Chrome headless** (topo e fim; busca; tema).
- [x] **Step 5: Commit** — `feat: amplia e moderniza o relatório HTML do Raio-X`.

### Task 5: Diálogo — cartões novos, busca única, ações e privacidade

**Files:**
- Modify: `cleanix/dialogs.py`
- Modify: `cleanix/styles.css`
- Modify: `cleanix/locale/{pt_BR,en,es}.json`
- Test: smoke em `/tmp` (não versionado)

**Interfaces:**
- Consumes: novos campos do snapshot; `xray.build_report_html(..., redact=...)`.
- Produces: cartões Rede/Sistema; alertas no resumo; `self.global_search`; botões “Mostrar todos”; `self.redact_check`; `self.spinner`.

- [x] **Step 1: Implementar cartões Rede e Sistema** (textos, copiar, sem senha).
- [x] **Step 2: Resumo com destaques** — linha destacada quando houver alertas.
- [x] **Step 3: Programas** — busca global, “Mostrar todos” por origem, tamanhos.
- [x] **Step 4: UX** — spinner, “Atualizado às”, Atualizar no rodapé, Copiar, Expandir/Recolher tudo, `Esc`.
- [x] **Step 5: Exportação** — checkbox de privacidade (padrão ligado) passado ao HTML; manter abertura automática.
- [x] **Step 6: Smoke GTK** — abrir diálogo, expandir tudo, filtrar, exportar com coleta simulada e conferir HTML.
- [x] **Step 7: Commit** — `feat: melhora a experiência e a privacidade do Raio-X`.

### Task 6: Verificação final e documentação

- [x] **Step 1:** `python3 -m unittest discover -s tests -v` (esperado: todos OK).
- [x] **Step 2:** `tools/check_language.py` e `tools/check_layout.py` OK.
- [x] **Step 3:** Atualizar `README.md` (privacidade, rede/sistema/discos, tamanhos, ações do HTML).
- [x] **Step 4:** Commit `docs: documenta as melhorias do Raio-X` e `git push origin feat/funcionalidades-reais`.
