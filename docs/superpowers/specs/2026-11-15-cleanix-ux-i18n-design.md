# Cleanix — reorganização da interface e três idiomas (design)

Data: 2026-11-15
Status: aguardando aprovação

## Intenção

O Cleanix já limpa de verdade, mas a tela inicial e os menus se repetem e
misturam inglês com português. O pedido é uma revisão geral de menus e painéis
para que um usuário leigo entenda o que cada coisa faz, e o programa deve
funcionar em **português (pt-BR), inglês (en) e espanhol (es)**.

A reorganização escolhida foi o **caminho A**: manter os diálogos como estão e
arrumar navegação, ordem dos painéis, nomes e duplicatas. Transformar o menu em
páginas reais (caminho B) fica para outra rodada.

## Objetivos

- Deixar o menu lateral todo em um idioma só, com nomes claros para leigo.
- Ter **uma entrada por ação**: nada de três botões abrindo o mesmo diálogo.
- Colocar a ação principal (revisar e limpar) no topo, perto do espaço
  recuperável.
- Remover painéis duplicados e checkboxes que não fazem nada na tela inicial.
- Renomear ações técnicas do Otimizador para linguagem simples.
- Trocar as ações opostas “Desktop”/“Performance” por um switch de animações.
- Mostrar a versão real da distribuição no rodapé.
- Traduzir toda a interface para pt-BR, en e es, com troca imediata em
  Configurações.
- Formatar números e datas conforme o idioma (1.234,5 em pt/es; 1,234.5 em en).

## Não-objetivos (nesta rodada)

- Transformar o menu em páginas/views dentro da janela (caminho B).
- gettext, arquivos `.po`/`.mo` ou dependência de ferramentas externas.
- Traduzir saída de comandos do sistema (apt, journalctl, fstrim) nem logs.
- Traduzir para idiomas além dos três pedidos.
- Suporte a RTL.
- Trocar o idioma automaticamente enquanto o app está aberto (só detecção na
  abertura e escolha manual depois).

## Anti-objetivos

- Alterar o comportamento de varredura/limpeza ou a allowlist de segurança.
- Esconder avisos de segurança para “deixar mais bonito”.
- Traduzir caminhos, comandos ou nomes de categorias internas.
- Quebrar o histórico já gravado (as entradas continuam guardando chaves).
- Exigir reiniciar o app para trocar de idioma.

## Restrições

- GTK4 + PyGObject + Cairo, sem dependência nova.
- Python 3.10+ (ambiente atual: 3.14).
- App roda direto do código (`python3 -m cleanix.main`), sem etapa de build.
- Tela de 1366×768; textos em inglês/espanhol podem ficar maiores.
- Testes existentes precisam continuar passando (forçando pt-BR quando
  verificam texto).

## Abordagens consideradas

### Interface

1. **Caminho A — reorganizar mantendo diálogos (escolhida).**
   Traduzir o menu, deixar uma entrada por ação, reordenar painéis, remover
   duplicatas e renomear ações. Risco baixo, resolve o que mais confunde.

2. **Caminho B — menu vira páginas reais.**
   Rejeitada nesta rodada: exige refatorar a janela e todos os diálogos para
   views, aumenta o risco e mistura com a tradução.

### Idiomas

1. **Catálogos JSON + camada própria (escolhida).**
   `cleanix/i18n.py` carrega `cleanix/locale/<código>.json`, com `t()` para
   textos e `tn()` para plural. Sem build, fácil de testar, troca imediata.

2. **gettext (`.po`/`.mo`).**
   Rejeitada: adiciona etapa de compilação e arquivos binários ao app, sem
   ganho nesta escala.

## Desenho

### Menu lateral

| Item | Ícone | Ação |
|------|-------|------|
| Início | `go-home-symbolic` | tela atual (permanece destacado) |
| Limpeza | `edit-clear-symbolic` | abre o diálogo de revisão/limpeza |
| Otimização | `utilities-system-monitor-symbolic` | abre o diálogo do Otimizador |
| Ajustes | `emblem-system-symbolic` | abre o diálogo de ajustes |
| — separador — | | |
| Histórico | `document-open-symbolic` | abre o histórico completo |
| Ajuda e Sobre | `help-about-symbolic` | um único diálogo com ajuda + versão |

- Os subtítulos em inglês (“(Limpeza)”, etc.) saem.
- “Configurações” continua no canto direito da barra inferior, como hoje.
- “Ajuda” sai da barra inferior; “Sobre” sai do menu e vira “Ajuda e Sobre”.
- O rodapé deixa de ser fixo em “Ubuntu 22.04 LTS” e passa a ler
  `/etc/os-release` (`PRETTY_NAME`, com fallback para `NAME` + `VERSION_ID`).

### Tela inicial (ordem final)

1. **Saúde** — anel + “Última verificação” + métricas de disco livre, RAM e CPU
   (como hoje).
2. **Limpeza** — cartão principal:
   - “Espaço Recuperável” em destaque e o botão primário **“Revisar e limpar”**
     (substitui “Ver Detalhes...”).
   - Lista **somente leitura** das categorias, com nome e tamanho, e a rosca de
     distribuição. Sem checkboxes na tela inicial: a seleção acontece no
     diálogo de limpeza.
3. **Memória RAM** — usado/total, disponível, cache, gráfico ao vivo e botão
   “Liberar memória” (como hoje).
4. **Disco e CPU** — dois cartões lado a lado:
   - “Uso do Disco” com a rosca e a legenda usada/livre/total (como hoje).
   - “Uso de CPU” com o gráfico de linha, título explícito e o texto
     “X% agora · N núcleos”. Substitui o cartão “Sistema”, que não dizia o que
     o gráfico media.
   - O aviso “Tudo funcionando bem!” sai deste cartão (já existe no bloco de
     saúde).
5. **Últimas Ações** — como hoje, com link para o histórico.

O bloco “O que deseja fazer?” é removido: ele repetia o menu lateral. O bloco
“Categorias de Limpeza” com checkboxes também sai; a lista vira somente
leitura dentro do cartão de limpeza.

### Ações renomeadas

| Hoje | Novo (pt-BR) |
|------|--------------|
| APT Auto-clean | Limpar cache do APT |
| Journal Vacuum | Limpar logs antigos |
| fstrim | Otimizar SSD |
| Startup Apps | Aplicativos de inicialização |
| Memória RAM | Memória RAM (mantém) |

- As descrições continuam explicando o que acontece e quando a senha será
  pedida.
- Nomes internos de comando e chaves não mudam.

### Ajustes

`AdjustmentsDialog` deixa de ser uma lista de comandos e vira um diálogo com
dois switches, aplicados na hora e sem root:

1. **Animações do sistema** — lê e escreve
   `org.gnome.desktop.interface enable-animations`.
2. **Limpar lixeira e temporários antigos automaticamente** — lê e escreve
   `org.gnome.desktop.privacy remove-old-trash-files` e
   `remove-old-temp-files` juntos.

O estado inicial é lido com `gsettings get`; falhas aparecem no status do
diálogo, sem fechar. Isso elimina a contradição atual entre “Desktop” (liga) e
“Performance” (desliga).

### Ajuda e Sobre

Um único diálogo, com:
- o texto de ajuda de segurança (allowlist, `/tmp`, pastas-raiz);
- “Cleanix 1.0”, descrição curta e a versão real da distribuição.

O botão “Ajuda” da barra inferior é removido para não duplicar.

### Idiomas

#### Módulo `cleanix/i18n.py`

- Idiomas: `pt_BR`, `en`, `es`.
- `detect_language()`: lê `LC_ALL`, `LC_MESSAGES` e `LANG`, remove a codificação
  (`pt_BR.UTF-8` → `pt_BR`) e mapeia prefixos `pt`/`en`/`es`; qualquer outra
  coisa cai em `pt_BR`.
- `set_language(code)` valida o código e carrega o catálogo.
- `t(chave, **valores)`: busca no idioma atual; se faltar, cai em `pt_BR`; se
  ainda faltar, devolve a própria chave e registra um aviso no log.
- `tn(chave, n, **valores)`: usa `chave.one`/`chave.other` e injeta `{n}`.
- `format_number(valor, casas)` e `format_datetime(iso)` por idioma.

#### Catálogos

- `cleanix/locale/pt_BR.json`, `en.json`, `es.json`.
- Chaves planas com ponto, em inglês, por área:
  `app.subtitle`, `sidebar.cleanup`, `dashboard.recoverable`,
  `category.trash`, `clean.done`, `bytes.freed.one`, etc.
- Os três arquivos têm exatamente o mesmo conjunto de chaves.
- Textos com valores variáveis usam `{placeholders}`.
- Saída de comandos e logs não entram nos catálogos.

#### Números e datas

- `systeminfo.format_bytes` passa a usar o separador do idioma:
  pt/es `1.234,5 MB`; en `1,234.5 MB`.
- Unidades (`B`, `KB`, `MB`, `GB`, `TB`) são iguais nos três idiomas.
- Datas: pt/es `%d/%m/%Y %H:%M`; en `%m/%d/%Y %H:%M`.
- `history.format_timestamp` delega para `i18n.format_datetime`.

#### Categorias

- A UI mostra `t('category.' + cat.key)`; `Category.label` continua existindo
  como fallback em português, mas não é exibido.
- O histórico continua guardando as chaves (`trash`, `tmp`, ...), então
  entradas antigas seguem válidas em qualquer idioma.

#### Preferência e troca

- `Settings` ganha `language: str = ""` (vazio = detectar do sistema).
- `load_settings` passa a respeitar campos `str` (hoje só aceita `bool`).
- Na abertura, `main.py` carrega as preferências e chama
  `i18n.set_language(cfg.language or i18n.detect_language())` antes de criar a
  janela.
- Configurações ganha um seletor com **Português / English / Español** (nomes
  sempre no próprio idioma). A escolha é salva na hora.
- Ao trocar: salva, fecha o diálogo de Configurações e a janela principal é
  reconstruída no idioma novo (sem reiniciar o app, sem reescanear). Diálogos
  abertos antes da troca continuam no idioma antigo até serem fechados.
- A reconstrução limpa os dicionários de widgets (`cat_rows`,
  `metric_labels`, `metric_bars`, `action_buttons`, `history_rows`), reconstrói
  a UI e reaproveita `self.results` para repintar os dados. O histórico de
  amostras do gráfico de RAM é preservado.

### Arquivos afetados

| Arquivo | Mudança |
|---------|---------|
| `cleanix/i18n.py` | novo: detecção, catálogos, `t`, `tn`, números/datas |
| `cleanix/locale/*.json` | novo: catálogos pt_BR, en, es |
| `cleanix/cleanixwindow.py` | menu, ordem dos painéis, remoção de duplicatas, reconstrução por idioma |
| `cleanix/dialogs.py` | textos via `t`, ajustes com switches, ajuda/sobre unificados |
| `cleanix/scanner.py` | descrições/labels via chaves (sem mudar a lógica) |
| `cleanix/systeminfo.py` | formatação por idioma e leitura de `/etc/os-release` |
| `cleanix/history.py` | data por idioma |
| `cleanix/settings.py` | campo `language` |
| `cleanix/main.py` | aplica o idioma antes de abrir a janela |
| `README.md`, `implementation-status.md` | menu, painéis e idiomas |

## Testes

- `tests/test_i18n.py` (novo):
  - os três catálogos têm o mesmo conjunto de chaves;
  - `t()` cai para pt-BR e depois para a chave;
  - `tn()` escolhe singular/plural;
  - `format_number` e `format_datetime` nos três idiomas;
  - `detect_language()` com `LANG` simulado.
- `tests/test_settings.py`: ida e volta do campo `language`; valor inválido cai
  no padrão.
- Testes existentes que verificam texto passam a forçar
  `i18n.set_language('pt_BR')` e são atualizados para os novos nomes
  (“Aplicativos de inicialização” etc.).
- Teste de GUI (harness externo): trocar para `en`, reconstruir e conferir
  menu/painéis em inglês; voltar para pt-BR.
- `tools/screenshot.py` para conferir a nova ordem dos painéis.

## Riscos

- **Reconstruir a UI com timers rodando** pode deixar referência a widget
  antigo. Mitigação: reconstrução síncrona, dicionários limpos e teste de troca
  de idioma duas vezes seguidas.
- **Catálogos divergentes** com o tempo. Mitigação: teste de paridade de chaves.
- **Textos longos em inglês/espanhol** estourando botões na largura de 1366.
  Mitigação: rótulos curtos e `wrap` onde já existe.
- **Testes atuais dependem de texto em português.** Mitigação: forçar pt-BR e
  atualizar as expectativas.
- **`format_bytes` é usado em toda parte.** Mitigação: manter a assinatura e
  testar os três idiomas.

## Decisões deixadas para o construtor

- Texto exato das traduções (desde que fiéis e curtos).
- `Gtk.DropDown` ou três radios para o seletor de idioma.
- Nomes internos de funções/classes e organização dos helpers.
- Ajustes finos de CSS e espaçamento para os textos mais longos.
