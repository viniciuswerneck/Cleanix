# Status da Implementação - Cleanix

## Status: FUNCIONAL, SEGURO E FIEL AO MOCKUP ✓

A interface segue o `mocup.png`, com gráficos desenhados em **Cairo** (não são
imagens nem labels) e dados reais do sistema. A limpeza de caches do usuário
está implementada com allowlist, confirmação e histórico.

## Arquivos

| Arquivo | Função |
|---------|--------|
| `main.py` | Entry point (Gtk.Application) |
| `cleanixwindow.py` | Janela principal, varredura e limpeza |
| `dialogs.py` | Avisos, confirmação, detalhes, ações e configurações |
| `scanner.py` | Varredura e remoção segura (allowlist + cache do APT) |
| `execution.py` | Comandos locais e administrativos via `pkexec` |
| `memory.py` | Leitura de `/proc/meminfo` e liberação do cache da RAM |
| `systeminfo.py` | Disco, memória, CPU e formatação pt-BR |
| `history.py` | Histórico persistente em JSON |
| `autostart.py` | Leitura e ativação de apps de inicialização |
| `settings.py` | Preferências em `~/.config/cleanix/config.json` |
| `charts.py` | Widgets Cairo (anel, rosca, linha, barra) |
| `styles.css` | Tema GTK4 (cores, tipografia, cards, botões) |
| `tests/` | Testes `unittest` de sistema, scanner e histórico |
| `tools/screenshot.py` | Captura offscreen para verificação visual |

## Interface

- Barra superior: logo de vassoura, "Cleanix", subtítulo, botões de janela
  (fechar em círculo laranja com X).
- Menu lateral 228px: Início, Cleaner, Optimizer, Adjustments, Histórico,
  Sobre + rodapé Ubuntu 22.04 LTS.
- Bloco 1 (Saúde): anel que muda de cor e glifo conforme o espaço livre em
  disco, e métricas reais de disco, memória e CPU.
- Bloco 2: Espaço Recuperável real, rosca de uso do disco e gráfico de linha
  com amostras de CPU.
- Bloco 3: Limpeza Inteligente (abre os detalhes), Otimização e Ajustes
  (abrem seus diálogos).
- Bloco 4: Categorias de Limpeza com tamanhos reais e checkboxes interativos;
  Últimas Ações com as três limpezas mais recentes.
- Barra inferior de status com Configurações e Ajuda.

## Funcionalidades reais

- **Varredura em segundo plano** ao abrir e após cada limpeza.
- **Categorias:** lixeira, miniaturas, cache dos navegadores, `/tmp` do usuário
  e cache do APT. O APT é marcável e, na limpeza, pede a senha de administrador
  e roda `apt-get clean`.
- **Limpeza:** confirmação com total selecionado, execução em thread e
  relatório final. Navegadores abertos geram aviso, mas não bloqueiam.
- **Histórico:** até 200 entradas, exibidas em diálogo e no cartão "Últimas
  Ações". Pode ser desligado em Configurações.
- **Otimizador:** limpeza do APT (`apt-get autoremove` + `clean`), journal
  vacuum de 7 dias, `fstrim -av`, liberação do cache da RAM em diálogo próprio
  e gerenciador de Startup Apps. As ações administrativas rodam por
  `pkexec /usr/bin/bash -c`, com confirmação antes.
- **Memória RAM:** mostra o cache reclamável a partir de `/proc/meminfo` e,
  com confirmação, roda `sync && echo 3 > /proc/sys/vm/drop_caches` via
  `pkexec`. Fica fora do Cleaner para não misturar memória com limpeza de disco.
- **Startup Apps:** lista `/etc/xdg/autostart` e `~/.config/autostart` e
  ativa/desativa por interruptor, sem root (override `Hidden=true`).
- **Ajustes:** animações do GNOME e limpeza automática de lixeira/temporários,
  aplicados por `gsettings` como o próprio usuário.
- **Configurações:** "confirmar antes de limpar" e "guardar histórico",
  salvos em `~/.config/cleanix/config.json`.
- **Log:** tudo em `~/.local/state/cleanix/cleanix.log`.
- **Segurança:** allowlist fechada, `realpath`/`commonpath`, sem seguir links
  simbólicos, raízes preservadas, `/tmp` com idade mínima de 10 minutos e
  exclusão de arquivos abertos.

## Gráficos (Cairo)

- `HealthRing` – anel com glow e glifo (check, "!" ou "×").
- `DonutChart` – rosca com segmentos coloridos e texto central via Overlay.
- `LineChart` – linha com área preenchida e grade; estado vazio sem área.
- `ProgressBar` – barras de progresso arredondadas.
- `make_trash_illustration` – lixeira lilás (disponível, não usada).

## Como executar

```bash
cd /home/vinicius/dev/app/cleanix
python3 -m cleanix.main
```

## Testes

```bash
python3 -m unittest discover -s tests -v
```

## Observações

- O programa foi renomeado de **LimpaLinux** para **Cleanix** (pacote Python
  `cleanix`, janela `CleanixWindow`, app id `br.cleanix.Cleanix`).
- O tamanho ideal é 1536x1040; em telas menores a janela se ajusta à tela e
  é maximizada, ficando abaixo da barra superior do Ubuntu. O conteúdo rola.
- A fonte Inter é usada se estiver instalada; senão cai para Ubuntu/Cantarell.
- Ícones de conteúdo são emojis; ícones do menu e botões usam ícones simbólicos
  do tema.
- `ui.py`, `safety.py` e `utils.py` são legado GTK3 não utilizado.

## Pendências

- [ ] swappiness e governador de CPU (exigem root e mexem em `sysctl`/`cpufreq`)
- [ ] Destacar no menu lateral a seção em uso (hoje "Início" fica fixo)
- [ ] Substituir emojis por ícones vetoriais próprios (opcional, fidelidade)

## Instalação

```bash
./install.sh   # cria atalho e ícone em ~/.local/share, sem root
```
