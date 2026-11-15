# Cleanix — Funcionalidades Reais: Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trocar os números e botões fictícios do Cleanix por dados reais do sistema e limpeza segura de lixo do usuário, com confirmação e histórico.

**Architecture:** Um motor puro em Python (`systeminfo`, `scanner`, `history`) sem dependência de GTK, testável com `unittest`, e uma camada de UI GTK4 (`charts`, `dialogs`, `cleanixwindow`) que consome esse motor. Varreduras e limpezas rodam em threads e atualizam a UI via `GLib.idle_add`.

**Tech Stack:** Python 3.14, GTK4 4.22, PyGObject, pycairo, `unittest` (stdlib).

**Spec:** `docs/superpowers/specs/2026-11-15-cleanix-funcionalidades-design.md`

## Global Constraints

- Python 3.10+; ambiente atual 3.14.4.
- Apenas GTK4, PyGObject e pycairo. Nenhuma dependência nova.
- Sem `sudo`, sem pedir senha, sem executar `rm -rf` via shell.
- Nenhuma remoção fora da allowlist (`$HOME` ou `/tmp`), nunca seguindo symlinks.
- Todo texto visível ao usuário em português do Brasil.
- Preservar o visual do mockup (paleta, fontes, cards, gráficos em Cairo).
- Testes com `unittest`; rodar com `python3 -m unittest discover -s tests -v`.

## Review Focus

- **Escape de caminho por `..` ou symlink:** apagar fora da raiz permitida deve ser impossível; testado na Task 3.
- **Arquivo em uso no `/tmp`:** não pode ser apagado nem contado; testado na Task 4.
- **Pastas-raiz das categorias:** nunca podem ser removidas; testado nas Tasks 3 e 4.
- **Histórico corrompido ou gravação parcial:** deve degradar para lista vazia e nunca deixar arquivo temporário; testado na Task 5.
- **UI travada durante varredura/limpeza:** operações precisam rodar fora da thread principal; verificado manualmente na Task 7.
- **Números do disco inconsistentes:** `usado + livre` deve fechar com o total; testado na Task 2.
- **Separador decimal em pt-BR:** vírgula, não ponto; testado na Task 2.

---

### Task 1: Harness de captura offscreen

**Files:**
- Create: `tools/screenshot.py`
- Test: execução manual (gera PNG)

**Interfaces:**
- Produces: `python3 tools/screenshot.py --out /tmp/opencode/cleanix.png [--scroll bottom]` — captura a janela e grava um PNG; imprime as dimensões.

- [ ] **Step 1: Criar `tools/screenshot.py`** adaptando o script usado hoje em `/tmp/opencode/snap.py`.

Requisitos exatos:
- `argparse` com `--out` (padrão `/tmp/opencode/cleanix.png`) e `--scroll` (`top` ou `bottom`).
- Importa `CleanixWindow` de `cleanix.cleanixwindow` após inserir a raiz do repo em `sys.path`.
- Usa `Gtk.WidgetPaintable.new(win)`, `Gtk.Snapshot.new()`, `paintable.snapshot(snap, w, h)`, `snap.to_node()`, `node.draw(cairo.Context(surface))`, `surface.write_to_png(out)`.
- Com `--scroll bottom`, encontra o `Gtk.ScrolledWindow` recursivamente, posiciona o ajuste vertical no fim e espera 600 ms antes de capturar.
- Imprime `salvo <out> <w>x<h>` e sai com código 0.

- [ ] **Step 2: Rodar o harness**

Run: `python3 tools/screenshot.py --out /tmp/opencode/task1.png`
Expected: imprime `salvo /tmp/opencode/task1.png 1321x736` (ou largura/altura da tela) e o arquivo existe.

- [ ] **Step 3: Commit**

```bash
git add tools/screenshot.py
git commit -m "tools: harness de captura offscreen"
```

---

### Task 2: `systeminfo` — disco, memória, CPU e formatação

**Files:**
- Create: `cleanix/systeminfo.py`
- Create: `tests/__init__.py`
- Create: `tests/test_systeminfo.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `@dataclass(frozen=True) DiskInfo(total: int, used: int, free: int, percent_used: float)`
  - `@dataclass(frozen=True) MemInfo(total: int, used: int, available: int, percent_used: float)`
  - `format_bytes(n: int) -> str`
  - `format_percent(value: float, decimals: int = 0) -> str`
  - `get_disk_info(path: str = "/") -> DiskInfo`
  - `parse_meminfo(text: str) -> MemInfo`
  - `get_mem_info() -> MemInfo`
  - `parse_cpu_times(text: str) -> tuple[int, int]` → `(busy, total)`
  - `read_cpu_times() -> tuple[int, int]`
  - `sample_cpu(prev: tuple[int, int] | None) -> tuple[float, tuple[int, int]]` → `(percent_used, novo_sample)`; `percent_used` é `0.0` quando `prev` é `None`.
  - `health_state(percent_free: float) -> str` → `"ok"` (≥20), `"warn"` (10–19.99), `"bad"` (<10).

Regras exatas:
- `format_bytes`: unidades `B, KB, MB, GB, TB` (base 1024). Sem casas para `B`; duas casas para valores < 10; uma casa para 10–99; zero casas para ≥ 100. Separador decimal vírgula. Exemplos: `0 → "0 B"`, `1024 → "1,00 KB"`, `78,4 GB → "78,4 GB"`, `2,48 GB → "2,48 GB"`.
- `get_disk_info`: `statvfs`; `total = f_blocks`, `free = f_bavail`, `used = total - free`, todos multiplicados por `f_frsize`. `percent_used = 100 * used / total` (0 se total for 0). Garante `used + free == total`.
- `parse_meminfo`: lê `MemTotal` e `MemAvailable` em kB (×1024). `used = total - available`; `percent_used = 100 * used / total`.
- `parse_cpu_times`: primeira linha começando com `cpu `; soma todos os campos numéricos como `total`; `busy = total - idle - iowait`.
- `sample_cpu`: chama `read_cpu_times`; se `prev` for `None`, retorna `(0.0, atual)`; senão `percent = 100 * (busy_atual - busy_prev) / (total_atual - total_prev)`, `0.0` se o delta total for 0.
- `health_state`: `>= 20 → "ok"`, `>= 10 → "warn"`, senão `"bad"`.

- [ ] **Step 1: Escrever os testes que falham**

```python
# tests/test_systeminfo.py
import unittest
from cleanix import systeminfo as si


class FormatBytesTest(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(si.format_bytes(0), "0 B")

    def test_bytes(self):
        self.assertEqual(si.format_bytes(999), "999 B")

    def test_kilobytes(self):
        self.assertEqual(si.format_bytes(1024), "1,00 KB")

    def test_gigabytes_one_decimal(self):
        self.assertEqual(si.format_bytes(int(78.4 * 1024**3)), "78,4 GB")

    def test_gigabytes_two_decimals(self):
        self.assertEqual(si.format_bytes(int(2.48 * 1024**3)), "2,48 GB")


class ParseMeminfoTest(unittest.TestCase):
    TEXT = ("MemTotal:       16000000 kB\n"
            "MemFree:         2000000 kB\n"
            "MemAvailable:    6000000 kB\n")

    def test_used_and_percent(self):
        info = si.parse_meminfo(self.TEXT)
        self.assertEqual(info.total, 16000000 * 1024)
        self.assertEqual(info.available, 6000000 * 1024)
        self.assertEqual(info.used, 10000000 * 1024)
        self.assertAlmostEqual(info.percent_used, 62.5)


class ParseCpuTimesTest(unittest.TestCase):
    TEXT = "cpu  100 0 100 800 0 0 0 0 0 0\ncpu0 1 2 3 4\n"

    def test_busy_and_total(self):
        busy, total = si.parse_cpu_times(self.TEXT)
        self.assertEqual(busy, 200)
        self.assertEqual(total, 1000)


class SampleCpuTest(unittest.TestCase):
    def test_first_sample_is_zero(self):
        percent, sample = si.sample_cpu(None)
        self.assertEqual(percent, 0.0)
        self.assertIsInstance(sample, tuple)


class HealthStateTest(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual(si.health_state(50), "ok")
        self.assertEqual(si.health_state(20), "ok")
        self.assertEqual(si.health_state(19.9), "warn")
        self.assertEqual(si.health_state(10), "warn")
        self.assertEqual(si.health_state(9.9), "bad")


class DiskInfoTest(unittest.TestCase):
    def test_used_plus_free_is_total(self):
        info = si.get_disk_info("/")
        self.assertEqual(info.used + info.free, info.total)
        self.assertGreaterEqual(info.percent_used, 0)
        self.assertLessEqual(info.percent_used, 100)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python3 -m unittest tests.test_systeminfo -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'cleanix.systeminfo'`.

- [ ] **Step 3: Implementar `cleanix/systeminfo.py`** com as assinaturas e regras acima.

- [ ] **Step 4: Rodar e ver passar**

Run: `python3 -m unittest tests.test_systeminfo -v`
Expected: PASS em todos os testes.

- [ ] **Step 5: Commit**

```bash
git add cleanix/systeminfo.py tests/__init__.py tests/test_systeminfo.py
git commit -m "feat: dados reais de disco, memória e CPU"
```

---

### Task 3: `scanner` — categorias, allowlist e limpeza de caches

**Files:**
- Create: `cleanix/scanner.py`
- Create: `tests/test_scanner.py`

**Interfaces:**
- Consumes: `os`, `stat`, `time`, `pathlib`.
- Produces:
  - `@dataclass(frozen=True) Category(key: str, label: str, roots: tuple[str, ...], kind: str, requires_admin: bool = False, min_age: int = 0)`
  - `build_categories(home: Path = Path.home()) -> tuple[Category, ...]`
  - `CATEGORIES: tuple[Category, ...]`
  - `@dataclass(frozen=True) ScanResult(key: str, bytes: int = 0, files: int = 0, errors: int = 0, available: bool = True)`
  - `@dataclass(frozen=True) CleanReport(bytes: int, files: int, errors: int, per_category: dict[str, ScanResult])`
  - `is_within(path: str, roots: Iterable[str]) -> bool`
  - `open_paths() -> set[str]`
  - `proc_available() -> bool`
  - `scan_category(cat: Category, now: float | None = None, open_set: set[str] | None = None) -> ScanResult`
  - `scan_all(categories: tuple[Category, ...] = CATEGORIES, now: float | None = None, open_set: set[str] | None = None) -> dict[str, ScanResult]`
  - `clean_category(cat: Category, now: float | None = None, open_set: set[str] | None = None) -> ScanResult`
  - `clean_selected(keys: Iterable[str], categories: tuple[Category, ...] = CATEGORIES, now: float | None = None, open_set: set[str] | None = None) -> CleanReport`

Categorias exatas em `build_categories`:

| key | label | roots | kind | flags |
|-----|-------|-------|------|-------|
| `trash` | Lixeira do Sistema | `home/.local/share/Trash/files`, `home/.local/share/Trash/info` | `trash` | — |
| `thumbnails` | Miniaturas de Imagens | `home/.cache/thumbnails` | `cache` | — |
| `browsers` | Cache dos Navegadores | `home/.cache/{google-chrome,chromium,mozilla/firefox,brave-browser,microsoft-edge,vivaldi}` | `cache` | — |
| `tmp` | Arquivos Temporários | `/tmp` | `tmp` | `min_age=600` |
| `apt` | Cache do APT | `/var/cache/apt/archives` | `cache` | `requires_admin=True` |

Regras exatas:
- `is_within`: `real = os.path.realpath(path)`; para cada raiz, `r = os.path.realpath(root)`; retorna `True` se `os.path.commonpath([real, r]) == r`. Qualquer erro → `False`.
- Varredura: `os.walk(root, followlinks=False)`; só `stat.S_ISREG` via `os.lstat` entra em `bytes`/`files`; symlinks e diretórios são ignorados. Cada arquivo passa por `is_within(p, (root,))`.
- `requires_admin=True` → retorna `ScanResult(key, available=False)` sem varrer.
- `available=True` se a raiz existir e for diretório; caso contrário `available=False` com zeros.
- Erros de `OSError` incrementam `errors` e não interrompem.
- `clean_category`: mesma caminhada da varredura; revalida `is_within` antes de cada `os.unlink`; depois remove diretórios vazios de baixo para cima (`os.walk(topdown=False, followlinks=False)`), nunca a raiz.
- `clean_selected`: roda `clean_category` para cada key, agrega `bytes/files/errors` e preenche `per_category`.
- `open_paths`: lê `/proc/<pid>/cwd` e `/proc/<pid>/fd/*` com `os.readlink` + `os.path.realpath`; ignora `OSError`. `proc_available`: `Path("/proc/self/fd").is_dir()`.

- [ ] **Step 1: Escrever os testes que falham**

```python
# tests/test_scanner.py
import os
import tempfile
import time
import unittest
from pathlib import Path

from cleanix import scanner


def cache_cat(root: str) -> scanner.Category:
    return scanner.Category(key="cache", label="Teste", roots=(root,), kind="cache")


class IsWithinTest(unittest.TestCase):
    def test_inside(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a", "b.txt")
            os.makedirs(os.path.dirname(p))
            open(p, "w").close()
            self.assertTrue(scanner.is_within(p, [d]))

    def test_dotdot_escape(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(scanner.is_within(os.path.join(d, "..", "x"), [d]))

    def test_symlink_escape(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as out:
            os.symlink(out, os.path.join(d, "link"))
            self.assertFalse(scanner.is_within(os.path.join(d, "link", "x"), [d]))


class ScanCacheTest(unittest.TestCase):
    def test_counts_regular_files(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "a"), "wb").write(b"x" * 10)
            os.makedirs(os.path.join(d, "sub"))
            open(os.path.join(d, "sub", "b"), "wb").write(b"y" * 5)
            r = scanner.scan_category(cache_cat(d), open_set=set())
            self.assertEqual((r.files, r.bytes), (2, 15))
            self.assertTrue(r.available)

    def test_ignores_symlinks(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as out:
            open(os.path.join(out, "big"), "wb").write(b"z" * 100)
            os.symlink(os.path.join(out, "big"), os.path.join(d, "link"))
            r = scanner.scan_category(cache_cat(d), open_set=set())
            self.assertEqual((r.files, r.bytes), (0, 0))


class CleanCacheTest(unittest.TestCase):
    def test_removes_files_keeps_root(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "a"), "wb").write(b"x" * 10)
            os.makedirs(os.path.join(d, "sub"))
            open(os.path.join(d, "sub", "b"), "wb").write(b"y" * 5)
            r = scanner.clean_category(cache_cat(d), open_set=set())
            self.assertEqual((r.files, r.bytes), (2, 15))
            self.assertTrue(os.path.isdir(d))
            self.assertEqual(os.listdir(d), [])


class RequiresAdminTest(unittest.TestCase):
    def test_apt_is_unavailable_and_not_scanned(self):
        cat = scanner.Category("apt", "Cache do APT",
                               ("/var/cache/apt/archives",), "cache",
                               requires_admin=True)
        r = scanner.scan_category(cat)
        self.assertFalse(r.available)
        self.assertEqual((r.bytes, r.files), (0, 0))
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python3 -m unittest tests.test_scanner -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'cleanix.scanner'`.

- [ ] **Step 3: Implementar `cleanix/scanner.py`** com as assinaturas e regras acima.

- [ ] **Step 4: Rodar e ver passar**

Run: `python3 -m unittest tests.test_scanner -v`
Expected: PASS em todos os testes.

- [ ] **Step 5: Commit**

```bash
git add cleanix/scanner.py tests/test_scanner.py
git commit -m "feat: scanner seguro de caches com allowlist"
```

---

### Task 4: `scanner` — regras especiais de `/tmp`

**Files:**
- Modify: `cleanix/scanner.py`
- Modify: `tests/test_scanner.py`

**Interfaces:**
- Consumes: tudo da Task 3.
- Produces: nenhuma assinatura nova; `scan_category`/`clean_category` passam a aplicar `kind == "tmp"`.

Regras exatas para `kind == "tmp"`:
- Se `open_set` for `None` e `proc_available()` for `False`, retorna `ScanResult(key, available=False)`.
- Se `open_set` for `None`, usa `open_paths()`.
- Durante o `os.walk`, se `os.path.realpath(dirpath)` estiver em `open_set`, faz `dirs[:] = []` e ignora a subárvore inteira.
- Arquivo entra apenas se: regular, `st_uid == os.getuid()`, `st_mtime <= now - min_age`, e `os.path.realpath(path) not in open_set`.
- Após apagar, remove diretórios vazios de baixo para cima apenas se: não for raiz, `st_uid == os.getuid()`, `st_mtime <= now - min_age`, `realpath not in open_set` e `os.listdir(dir) == []`.
- `now` padrão é `time.time()`.

- [ ] **Step 1: Adicionar os testes que falham**

```python
# acrescentar em tests/test_scanner.py

class TmpRulesTest(unittest.TestCase):
    def _cat(self, root):
        return scanner.Category("tmp", "Temporários", (root,), "tmp", min_age=600)

    def test_old_file_counted_new_file_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.path.join(d, "old")
            new = os.path.join(d, "new")
            open(old, "wb").write(b"o" * 10)
            open(new, "wb").write(b"n" * 10)
            now = time.time()
            os.utime(old, (now - 700, now - 700))
            r = scanner.scan_category(self._cat(d), now=now, open_set=set())
            self.assertEqual((r.files, r.bytes), (1, 10))

    def test_open_file_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "inuse")
            open(p, "wb").write(b"x" * 10)
            now = time.time()
            os.utime(p, (now - 700, now - 700))
            r = scanner.scan_category(self._cat(d), now=now,
                                      open_set={os.path.realpath(p)})
            self.assertEqual(r.files, 0)

    def test_open_subtree_pruned(self):
        with tempfile.TemporaryDirectory() as d:
            sub = os.path.join(d, "live")
            os.makedirs(sub)
            p = os.path.join(sub, "f")
            open(p, "wb").write(b"x" * 10)
            now = time.time()
            os.utime(p, (now - 700, now - 700))
            r = scanner.scan_category(self._cat(d), now=now,
                                      open_set={os.path.realpath(sub)})
            self.assertEqual(r.files, 0)

    def test_clean_keeps_recent_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "recent")
            open(p, "wb").write(b"x" * 10)
            now = time.time()
            os.utime(p, (now - 60, now - 60))
            scanner.clean_category(self._cat(d), now=now, open_set=set())
            self.assertTrue(os.path.exists(p))

    def test_clean_prunes_empty_old_dirs_but_not_root(self):
        with tempfile.TemporaryDirectory() as d:
            sub = os.path.join(d, "olddir")
            os.makedirs(sub)
            f = os.path.join(sub, "f")
            open(f, "wb").write(b"x" * 10)
            now = time.time()
            os.utime(f, (now - 700, now - 700))
            os.utime(sub, (now - 700, now - 700))
            scanner.clean_category(self._cat(d), now=now, open_set=set())
            self.assertTrue(os.path.isdir(d))
            self.assertFalse(os.path.exists(sub))
```

Para o modo degradado, adicione no topo do arquivo:

```python
from unittest import mock
```

e o teste:

```python
    def test_proc_unavailable_disables_tmp(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(scanner, "proc_available", return_value=False):
                r = scanner.scan_category(self._cat(d))
            self.assertFalse(r.available)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python3 -m unittest tests.test_scanner.TmpRulesTest -v`
Expected: FAIL nos testes de idade/aberto/poda.

- [ ] **Step 3: Implementar as regras de `/tmp`** em `cleanix/scanner.py`.

- [ ] **Step 4: Rodar e ver passar**

Run: `python3 -m unittest tests.test_scanner -v`
Expected: PASS em todos os testes.

- [ ] **Step 5: Commit**

```bash
git add cleanix/scanner.py tests/test_scanner.py
git commit -m "feat: regras seguras para limpeza de /tmp"
```

---

### Task 5: `history` — histórico persistente

**Files:**
- Create: `cleanix/history.py`
- Create: `tests/test_history.py`

**Interfaces:**
- Consumes: `json`, `os`, `pathlib`, `datetime`.
- Produces:
  - `@dataclass(frozen=True) HistoryEntry(timestamp: str, bytes: int, files: int, categories: tuple[str, ...], errors: int)`
  - `history_path() -> Path` → `~/.local/share/cleanix/history.json`
  - `format_timestamp(iso: str) -> str` → `"15/11/2026 10:20"`
  - `load_history(path: Path | None = None) -> list[HistoryEntry]`
  - `append_entry(entry: HistoryEntry, path: Path | None = None) -> list[HistoryEntry]`
  - `clear_history(path: Path | None = None) -> None`
  - `MAX_ENTRIES = 200`

Regras exatas:
- `load_history`: arquivo ausente ou JSON inválido → `[]`; ignora entradas sem os campos obrigatórios.
- `append_entry`: carrega, acrescenta, mantém apenas as últimas `MAX_ENTRIES`, grava de forma atômica (arquivo `.tmp` + `os.replace`), cria diretórios-pai. Retorna a lista final.
- `clear_history`: remove o arquivo se existir.
- `format_timestamp`: `datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")`; em erro, retorna o texto original.

- [ ] **Step 1: Escrever os testes que falham**

```python
# tests/test_history.py
import tempfile
import unittest
from pathlib import Path

from cleanix import history


def entry(n: int) -> history.HistoryEntry:
    return history.HistoryEntry(
        timestamp="2026-11-15T10:20:00",
        bytes=n, files=1, categories=("trash",), errors=0)


class HistoryTest(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "h.json"
            history.append_entry(entry(100), path=p)
            self.assertEqual(history.load_history(path=p), [entry(100)])

    def test_missing_file_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(history.load_history(path=Path(d) / "nope.json"), [])

    def test_corrupt_file_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "h.json"
            p.write_text("{oops", encoding="utf-8")
            self.assertEqual(history.load_history(path=p), [])

    def test_caps_at_200(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "h.json"
            for i in range(205):
                history.append_entry(entry(i), path=p)
            loaded = history.load_history(path=p)
            self.assertEqual(len(loaded), 200)
            self.assertEqual(loaded[0].bytes, 5)
            self.assertEqual(loaded[-1].bytes, 204)

    def test_clear(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "h.json"
            history.append_entry(entry(1), path=p)
            history.clear_history(path=p)
            self.assertFalse(p.exists())

    def test_atomic_leaves_no_tmp_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "h.json"
            history.append_entry(entry(1), path=p)
            self.assertEqual(sorted(x.name for x in Path(d).iterdir()), ["h.json"])

    def test_format_timestamp(self):
        self.assertEqual(history.format_timestamp("2026-11-15T10:20:00"),
                         "15/11/2026 10:20")
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python3 -m unittest tests.test_history -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'cleanix.history'`.

- [ ] **Step 3: Implementar `cleanix/history.py`** com as assinaturas e regras acima.

- [ ] **Step 4: Rodar e ver passar**

Run: `python3 -m unittest tests.test_history -v`
Expected: PASS em todos os testes.

- [ ] **Step 5: Commit**

```bash
git add cleanix/history.py tests/test_history.py
git commit -m "feat: histórico persistente de limpezas"
```

---

### Task 6: `charts` — widgets atualizáveis

**Files:**
- Modify: `cleanix/charts.py`

**Interfaces:**
- Consumes: Cairo, `Gtk.DrawingArea`, `Gtk.Overlay`, `Gtk.Label`.
- Produces:
  - `class ProgressBar(Gtk.DrawingArea)` com `__init__(fraction: float = 0.0, color: str = "#20C957", width: int = 170, height: int = 14)`, `set_fraction(fraction: float)`, `set_color(color: str)`.
  - `class HealthRing(Gtk.DrawingArea)` com `__init__(size: int = 128)`, `set_state(state: str)` aceitando `"ok" | "warn" | "bad"`.
  - `class DonutChart(Gtk.Overlay)` com `__init__(segments: list[tuple[float, str]], center_markup: str = "", size: int = 150, thickness: int = 22)`, `set_segments(segments, center_markup: str | None = None)`.
  - `class LineChart(Gtk.DrawingArea)` com `__init__(width: int = 340, height: int = 110, color: str = "#20C957")`, `set_values(values: list[float])` (valores 0..1; menos de 2 pontos desenha linha reta no meio).
  - `make_bar(...) -> ProgressBar`, `make_health_ring(size=128) -> HealthRing`, `make_donut(...) -> DonutChart`, `make_line_chart(...) -> LineChart`, `make_trash_illustration(size=92)`.

Regras exatas:
- Manter as fábricas com os mesmos parâmetros usados hoje em `cleanixwindow.py`.
- `HealthRing`: `ok` usa `#20C957`/`#3EF07A` e desenha check; `warn` usa `#F5A623` e desenha `!`; `bad` usa `#F4510B` e desenha `×`. O desenho do glifo é feito com linhas/retângulos em Cairo (sem Pango).
- `DonutChart`: o texto central continua num `Gtk.Label` sobreposto, com markup Pango.
- `LineChart.set_values` redesenha grade, área translúcida e linha; `queue_draw()` após atualizar.

- [ ] **Step 1: Refatorar `cleanix/charts.py`** mantendo os nomes das fábricas e o desenho atual.

- [ ] **Step 2: Verificar que a janela ainda abre**

Run: `python3 tools/screenshot.py --out /tmp/opencode/task6.png`
Expected: `salvo ...` e a imagem mostra anel verde, rosca e gráfico de linha iguais aos de antes.

- [ ] **Step 3: Verificar visualmente o PNG** e confirmar que nada sumiu ou mudou de posição.

- [ ] **Step 4: Commit**

```bash
git add cleanix/charts.py
git commit -m "refactor: widgets de gráfico atualizáveis"
```

---

### Task 7: Diálogos e integração da janela

**Files:**
- Create: `cleanix/dialogs.py`
- Modify: `cleanix/cleanixwindow.py`
- Modify: `cleanix/styles.css`
- Modify: `README.md` (status)

**Interfaces:**
- Consumes: `scanner.Category`, `scanner.ScanResult`, `scanner.CleanReport`, `history.HistoryEntry`, `systeminfo.*`, `charts.*`.
- Produces:
  - `show_info(parent: Gtk.Window, title: str, message: str) -> None`
  - `confirm(parent: Gtk.Window, title: str, message: str, confirm_label: str, on_confirm: Callable[[], None]) -> None`
  - `class DetailsDialog(Gtk.Window)` com `__init__(parent, categories, results: dict[str, scanner.ScanResult], selected: set[str], on_clean: Callable[[set[str]], None])`
  - `class HistoryDialog(Gtk.Window)` com `__init__(parent, entries: list[history.HistoryEntry], on_clear: Callable[[], None])`
  - `CleanixWindow` mantém `self.results`, `self.selected`, `self.scan_time`, `self._busy`.

Regras exatas da janela:
- Ao construir: `self.categories = scanner.build_categories()`; `self.selected = {c.key for c in self.categories if not c.requires_admin}`; `self.results = {}`; `self.scan_time = None`.
- Guardar referências: `self.health_ring`, `self.disk_donut`, `self.line_chart`, `self.recoverable_label`, `self.cat_rows` (`dict[str, tuple[Gtk.CheckButton, Gtk.Label]]`), `self.history_rows`, `self.status_text`, `self.metric_labels` e `self.metric_bars`.
- Iniciar varredura 500 ms após abrir: `GLib.timeout_add(500, self._start_scan)`.
- `_start_scan`: se `_busy`, retorna; marca ocupado; status "Escaneando..."; roda `scanner.scan_all()` em `threading.Thread(daemon=True)`; resultado via `GLib.idle_add(self._scan_done, results)`.
- `_scan_done`: guarda `results`, `scan_time = datetime.now()`, atualiza métricas, cartão recuperável, lista de categorias, rosca e histórico; status "Pronto para ajudar seu sistema!"; libera botões.
- `_start_clean(keys)`: se vazio ou `_busy`, mostra info "Nada selecionado"; se a soma de `results[key].bytes` das categorias selecionadas for 0, mostra info "Nada para limpar" e não apaga nada; se `$HOME` não for gravável (`os.access`), mostra erro e não apaga nada; senão marca ocupado, status "Limpando...", roda `scanner.clean_selected(keys)` em thread, chama `history.append_entry(...)` com `datetime.now().isoformat(timespec="seconds")`, e via `GLib.idle_add(self._clean_done, report)`.
- A confirmação de limpeza inclui o aviso "Feche os navegadores para liberar mais espaço" quando `browsers` estiver entre as categorias selecionadas.
- Se a gravação do histórico falhar, mostra um aviso, mas não desfaz a limpeza já concluída.
- `_clean_done`: mostra resultado com `show_info` ("Limpeza concluída", `"X liberados, Y arquivos removidos"` + erros, se houver); atualiza histórico e dispara nova varredura.
- `_tick_cpu`: a cada 2000 ms, `percent, self._cpu_sample = systeminfo.sample_cpu(self._cpu_sample)`; atualiza label/barra e adiciona `percent / 100` ao `LineChart` (máximo 30 amostras). Retorna `True`.
- "Ver Detalhes..." e o cartão "Limpeza Inteligente" abrem `DetailsDialog` com `self.categories`, `self.results`, `self.selected`, `self._start_clean`.
- Checkboxes da lista principal: `Gtk.CheckButton`, marcados conforme `self.selected`; ao alternar, atualizam `self.selected`. Linha do APT mostra "Requer administrador" e fica desabilitada.
- "Otimização" e "Ajustes" chamam `show_info(..., "Disponível em breve", ...)`.
- "Ver Histórico →" abre `HistoryDialog`; ao limpar, `history.clear_history()` e atualiza a tela.
- Botões "Configurações" e "Ajuda" da barra inferior chamam `show_info` com texto curto.
- Enquanto `_busy`, os botões de ação ficam `set_sensitive(False)`.

Regras exatas dos diálogos:
- Usar `Gtk.AlertDialog` para info/confirmação (assíncrono, sem `run()`).
- `DetailsDialog`: modal, `transient_for=parent`, largura 560; título "Detalhes da Limpeza"; uma linha por categoria com nome, tamanho (`systeminfo.format_bytes`), nº de arquivos e checkbox; total selecionado no rodapé; botões "Cancelar" e "Limpar agora"; categorias indisponíveis ou `requires_admin` desabilitadas com o texto "Requer administrador".
- `HistoryDialog`: modal, largura 520; lista com data (`history.format_timestamp`), "X liberados" e nº de arquivos; estado vazio "Nenhuma limpeza registrada ainda"; botão "Limpar histórico" com confirmação.

- [ ] **Step 1: Criar `cleanix/dialogs.py`** com as assinaturas acima.

- [ ] **Step 2: Adicionar estilos em `cleanix/styles.css`** para `.dialog`, `.dialog-title`, `.dialog-row`, `.dialog-total`, `.btn-secondary`, `.btn-danger`, `.empty-text`, `.hist-row`. Usar apenas propriedades válidas de GTK4 (sem `width`/`height`).

- [ ] **Step 3: Integrar a janela** em `cleanix/cleanixwindow.py`, substituindo todos os valores fixos por dados reais.

- [ ] **Step 4: Rodar os testes**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS em todos os testes.

- [ ] **Step 5: Testar a limpeza em um HOME falso (sem tocar nos arquivos reais)**

```bash
mkdir -p /tmp/opencode/fakehome/.cache/thumbnails
dd if=/dev/zero of=/tmp/opencode/fakehome/.cache/thumbnails/velho bs=1024 count=10
touch -d "2 hours ago" /tmp/opencode/fakehome/.cache/thumbnails/velho
HOME=/tmp/opencode/fakehome XDG_CONFIG_HOME=/tmp/opencode/fakehome/.config \
  python3 tools/screenshot.py --out /tmp/opencode/task7.png
```

Expected: o app abre, mostra "10,0 KB" em Miniaturas e o botão "Ver Detalhes..." funciona.

- [ ] **Step 6: Verificar o fluxo completo manualmente** (abrir detalhes, desmarcar uma categoria, cancelar; depois limpar e ver o resultado e o histórico).

Run: `HOME=/tmp/opencode/fakehome python3 -m cleanix.main`
Expected: após limpar, o arquivo `velho` some, a miniatura mostra 0 B e o histórico ganha uma entrada.

- [ ] **Step 7: Commit**

```bash
git add cleanix/dialogs.py cleanix/cleanixwindow.py cleanix/styles.css README.md
git commit -m "feat: limpeza real com confirmação, dados do sistema e histórico"
```

---

### Task 8: Documentação e verificação final

**Files:**
- Modify: `README.md`
- Modify: `implementation-status.md`
- Modify: `docs/superpowers/specs/2026-11-15-cleanix-funcionalidades-design.md` (marcar aprovado)

- [ ] **Step 1: Atualizar o README** com o status real (dados reais, limpeza, categorias suportadas, o que exige admin, como rodar os testes).

- [ ] **Step 2: Atualizar `implementation-status.md`** removendo as pendências concluídas.

- [ ] **Step 3: Rodar a suíte completa**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS em todos os testes.

- [ ] **Step 4: Gerar as capturas finais**

```bash
python3 tools/screenshot.py --out preview_topo.png
python3 tools/screenshot.py --out preview_inferior.png --scroll bottom
```

- [ ] **Step 5: Conferir visualmente** que os números são reais e o layout continua fiel ao mockup.

- [ ] **Step 6: Commit e push**

```bash
git add README.md implementation-status.md docs preview_topo.png preview_inferior.png
git commit -m "docs: status final das funcionalidades reais"
git push
```
