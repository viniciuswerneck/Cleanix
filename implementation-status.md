# Status da Implementação - Cleanix

## Status: FUNCIONAL E FIEL AO MOCKUP ✓

A interface foi reconstruída seguindo o `mocup.png`, com gráficos reais
desenhados em **Cairo** (não são imagens nem labels de texto).

## Arquivos

| Arquivo | Função |
|---------|--------|
| `main.py` | Entry point (Gtk.Application) |
| `cleanixwindow.py` | Layout completo da janela |
| `charts.py` | Widgets desenhados em Cairo (anel, rosca, linha, barra, lixeira) |
| `styles.css` | Tema GTK4 (cores, tipografia, cards, botões) |
| `design-plan.md` | Especificação de design |
| `mocup.png` | Mockup de referência |

## O que já está fiel ao mockup

- Barra superior: logo de vassoura, "Cleanix", subtítulo, botões de janela
  (fechar em círculo laranja com X).
- Menu lateral 228px: Início (destacado em laranja), Cleaner, Optimizer,
  Adjustments, Histórico, Sobre + rodapé Ubuntu 22.04 LTS.
- Bloco 1 (Saúde): anel verde com brilho e check, título, e métricas
  Disco/Memória/CPU com barras verdes/azuis/roxas.
- Bloco 2: Espaço Recuperável (botão verde "Ver Detalhes..."), Uso do Disco
  (rosca azul/verde com "46%"), Sistema (gráfico de linha verde com área).
- Bloco 3: 3 ações (Limpeza Inteligente destacada com borda azul, Otimização,
  Ajustes) com setas circulares azuis.
- Bloco 4: Categorias de Limpeza (checkboxes + lista + rosca colorida "2,48 GB")
  e Últimas Ações (checks verdes + histórico + datas).
- Barra inferior de status com "Pronto para ajudar seu sistema!" e
  Configurações/Ajuda.

## Gráficos (Cairo)

- `make_health_ring` – anel verde com glow + check.
- `make_donut` – rosca com segmentos coloridos e texto central via Overlay.
- `make_line_chart` – linha com área preenchida e grade.
- `make_bar` – barras de progresso arredondadas.
- `make_trash_illustration` – lixeira lilás (disponível, não usada ainda).

## Como executar

```bash
cd /home/vinicius/dev/app/cleanix
python3 -m cleanix.main
```

## Observações

- O programa foi renomeado de **LimpaLinux** para **Cleanix** (pacote Python
  `cleanix`, janela `CleanixWindow`, app id `br.cleanix.Cleanix`).
- O tamanho ideal é 1536x1040; em telas menores a janela se ajusta à tela e
  é maximizada, ficando abaixo da barra superior do Ubuntu. O conteúdo rola.
- A fonte Inter é usada se estiver instalada; senão cai para Ubuntu/Cantarell.
- Ícones de conteúdo são emojis (paleta do sistema); ícones do menu e botões
  usam ícones simbólicos do tema.

## Pendências (funcionalidade, não aparência)

- [ ] Ligar botões a ações reais (limpeza, otimização, ajustes)
- [ ] Alimentar gráficos com dados reais do sistema (disco, RAM, CPU)
- [ ] Páginas internas de cada seção ao clicar no menu
- [ ] Substituir emojis por ícones vetoriais próprios (opcional, fidelidade)
