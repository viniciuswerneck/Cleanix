# Cleanix

Limpeza e otimização do sistema para Linux, com interface moderna em **GTK4**.

Inspirado no visual do CCleaner, o Cleanix reúne em uma única tela o estado de
saúde do sistema, o espaço recuperável, o uso do disco e atalhos para limpeza,
otimização e ajustes — tudo com gráficos desenhados em **Cairo**.

![Prévia da interface](preview_topo.png)

## Recursos da interface

- Anel de saúde do sistema com indicador visual.
- Métricas de disco, memória e CPU com barras de progresso.
- Rosca de uso do disco e gráfico de linha do sistema.
- Cartões de ação: Limpeza Inteligente, Otimização e Ajustes.
- Lista de categorias de limpeza e histórico das últimas ações.
- Tema escuro com a paleta do mockup original.

## Requisitos

- Python 3.10+
- GTK 4
- PyGObject (`python3-gi`)
- pycairo

No Ubuntu/Debian:

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 python3-cairo
```

## Como executar

```bash
python3 -m cleanix.main
```

## Estrutura

```
cleanix/
├── cleanix/
│   ├── __init__.py
│   ├── main.py            # entry point (Gtk.Application)
│   ├── cleanixwindow.py   # layout da janela
│   ├── charts.py          # widgets desenhados em Cairo
│   ├── styles.css         # tema GTK4
│   ├── safety.py          # utilitários de segurança (em integração)
│   ├── ui.py              # interface legada (em migração)
│   └── utils.py           # utilitários de sistema (em integração)
├── design-plan.md         # especificação de design
├── implementation-status.md
├── mocup.png              # mockup de referência
└── preview_*.png          # capturas reais do app
```

## Segurança

O objetivo é limpar apenas arquivos temporários e caches, sempre com
confirmação do usuário antes de remover qualquer coisa. As rotinas de limpeza
reais ainda estão em integração — hoje o app é focado na interface.

## Status

Interface fiel ao mockup e funcional. Próximos passos:

- [ ] Alimentar os gráficos com dados reais do sistema (disco, RAM, CPU)
- [ ] Ligar os botões às rotinas de limpeza e otimização
- [ ] Páginas internas de cada seção
- [ ] Ícones vetoriais próprios no lugar dos emojis
