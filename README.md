# Cleanix

Limpeza e otimização do sistema para Linux, com interface moderna em **GTK4**.

Inspirado no visual do CCleaner, o Cleanix reúne em uma única tela o estado de
saúde do sistema, o espaço recuperável, o uso do disco e atalhos para limpeza,
otimização e ajustes — tudo com gráficos desenhados em **Cairo** e dados reais
do sistema.

![Prévia da interface](preview_topo.png)

## Recursos

- Dados reais de disco, memória e CPU, atualizados em segundo plano.
- Anel de saúde baseado no espaço livre em disco (verde, amarelo ou vermelho).
- Rosca de uso do disco e gráfico de linha com as últimas amostras de CPU.
- Varredura segura de quatro categorias do usuário:
  - Lixeira do sistema;
  - miniaturas de imagens;
  - cache dos navegadores (Chrome, Chromium, Firefox, Brave, Edge e Vivaldi);
  - arquivos temporários do usuário em `/tmp`.
- Diálogo de detalhes com tamanho e número de arquivos por categoria.
- Confirmação explícita antes de remover, com aviso quando há navegadores
  selecionados.
- Relatório ao final da limpeza (bytes liberados, arquivos removidos e erros).
- Histórico persistente das limpezas em
  `~/.local/share/cleanix/history.json` (últimas 200 entradas).
- Cache do APT aparece desabilitado com o texto "Requer administrador".
- Otimização e Ajustes mostram "Disponível em breve", sem simular ações.

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

## Como rodar os testes

```bash
python3 -m unittest discover -s tests -v
```

## Segurança

A limpeza é limitada a uma allowlist fechada: lixeira, miniaturas, cache dos
navegadores e arquivos temporários do usuário em `/tmp`. Nada fora dessas
pastas é tocado.

- Links simbólicos nunca são seguidos e cada caminho é revalidado antes da
  remoção.
- As pastas-raiz das categorias nunca são removidas.
- Em `/tmp`, só saem arquivos do próprio usuário com mais de 10 minutos,
  ignorando arquivos abertos, diretórios usados como `cwd` e suas subárvores.
- Falhas em um arquivo não interrompem o restante; os erros são somados e
  exibidos no relatório.
- Se `$HOME` não for gravável, a limpeza é cancelada.
- Nada é apagado sem confirmação explícita.

## Estrutura

```
cleanix/
├── cleanix/
│   ├── __init__.py
│   ├── main.py            # entry point (Gtk.Application)
│   ├── cleanixwindow.py   # janela principal e integração
│   ├── dialogs.py         # avisos, confirmação, detalhes e histórico
│   ├── scanner.py         # varredura e limpeza segura (allowlist)
│   ├── systeminfo.py      # disco, memória, CPU e formatação pt-BR
│   ├── history.py         # histórico persistente
│   ├── charts.py          # widgets desenhados em Cairo
│   └── styles.css         # tema GTK4
├── tests/                 # testes unittest
├── tools/
│   └── screenshot.py      # captura offscreen reproduzível
├── docs/                  # design e plano de implementação
├── mocup.png              # mockup de referência
└── preview_*.png          # capturas reais do app
```

Os arquivos `cleanix/ui.py`, `cleanix/safety.py` e `cleanix/utils.py` são
legado da versão GTK3, não são usados pelo aplicativo atual e não devem ser
reutilizados.

## Status

- [x] Dados reais do sistema (disco, RAM, CPU) e gráficos atualizáveis
- [x] Limpeza real com confirmação, relatório e histórico
- [ ] Otimização e ajustes do sistema (mostram "Disponível em breve")
- [ ] Páginas internas de cada seção
- [ ] Ícones vetoriais próprios no lugar dos emojis
