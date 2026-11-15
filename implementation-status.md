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
| `dialogs.py` | Avisos, confirmação, detalhes e histórico |
| `scanner.py` | Varredura e remoção segura (allowlist) |
| `systeminfo.py` | Disco, memória, CPU e formatação pt-BR |
| `history.py` | Histórico persistente em JSON |
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
  ("Disponível em breve").
- Bloco 4: Categorias de Limpeza com tamanhos reais e checkboxes interativos;
  Últimas Ações com as três limpezas mais recentes.
- Barra inferior de status com Configurações e Ajuda.

## Funcionalidades reais

- **Varredura em segundo plano** ao abrir e após cada limpeza.
- **Categorias:** lixeira, miniaturas, cache dos navegadores e `/tmp` do
  usuário. O cache do APT aparece como "Requer administrador".
- **Limpeza:** confirmação com total selecionado, execução em thread e
  relatório final. Navegadores abertos geram aviso, mas não bloqueiam.
- **Histórico:** até 200 entradas, exibidas em diálogo e no cartão "Últimas
  Ações".
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

- [ ] Otimização do sistema (governador de CPU, swappiness, TRIM)
- [ ] Ajustes do sistema com privilégios administrativos
- [ ] Páginas internas de cada seção ao clicar no menu
- [ ] Substituir emojis por ícones vetoriais próprios (opcional, fidelidade)
