# Cleanix — Funcionalidades reais (design)

Data: 2026-11-15
Status: aguardando aprovação

## Intenção

Hoje o Cleanix é uma interface fiel ao mockup, mas todos os números e ações são
fictícios. O objetivo é transformar a tela em um limpador real e seguro para
Ubuntu: ler o estado do sistema, escanear lixo de verdade, mostrar o tamanho
real de cada categoria e apagar somente o que o usuário confirmar.

O pedido central do usuário é **"não estragar nada"**. Toda decisão abaixo é
subordinada a isso.

## Objetivos

- Exibir dados reais de disco, memória e CPU.
- Escanear e exibir o tamanho real de 4 categorias de lixo do usuário.
- Limpar as categorias escolhidas após confirmação explícita.
- Registrar cada limpeza em um histórico persistente e exibi-lo na tela.
- Manter a janela responsiva durante varreduras (nada de travar a UI).

## Não-objetivos (nesta rodada)

- Limpeza de caches do sistema que exigem root (APT, journal, `/var`).
- Otimização (troca de governador de CPU, swappiness, TRIM etc.).
- Ajustes de sistema (gsettings, temas, serviços).
- Agendamento automático de limpeza.
- Limpeza de arquivos pessoais fora das categorias abaixo.

Essas seções continuarão visíveis, mas com uma mensagem clara de
"disponível em breve" — nada de botão que finge funcionar.

## Anti-objetivos

- Apagar qualquer caminho fora da allowlist fechada.
- Seguir links simbólicos para fora das raízes permitidas.
- Limpar `/tmp` inteiro ou arquivos de outros usuários/root.
- Executar `rm -rf` via shell.
- Pedir senha de administrador.
- Apagar arquivos abertos por processos em execução.

## Restrições

- GTK4 + PyGObject + Cairo, sem dependências novas de UI.
- Python 3.10+ (ambiente atual: 3.14.4).
- Sem sudo nesta rodada.
- O app precisa continuar funcionando offline e sem daemon.

## Abordagens consideradas

1. **Novo motor com allowlist fechada (escolhida).**
   Módulos pequenos e testáveis, cada categoria declara raízes permitidas e
   regras próprias. A UI só chama funções desse motor. É a única opção que
   permite garantir "não apagar fora daqui" e testar isso automaticamente.

2. **Reaproveitar `utils.py` / `safety.py`.**
   Rejeitada: varrem `~/.cache` e `/tmp` inteiros, usam diálogos GTK3
   incompatíveis com GTK4 e tratam `/var` como protegido (o que impede limpar
   APT). Corrigir seria mais arriscado do que reescrever.

3. **Delegar para ferramentas externas (BleachBit, Stacer).**
   Rejeitada: adiciona dependência pesada, exige root para metade das ações e
   não dá o controle fino de segurança que o pedido exige.

## Desenho

### Módulos novos

| Arquivo | Responsabilidade |
|---------|------------------|
| `cleanix/systeminfo.py` | disco, memória, CPU, contagem de núcleos |
| `cleanix/scanner.py` | categorias, varredura, validação de caminho, remoção |
| `cleanix/history.py` | leitura/gravação do histórico em JSON |
| `cleanix/dialogs.py` | diálogos GTK4 de detalhes, confirmação e resultado |

`cleanix/charts.py` será refatorado para widgets atualizáveis
(`HealthRing`, `DonutChart`, `LineChart`, `ProgressBar`), mantendo as funções
de fábrica atuais para não quebrar chamadas existentes.

`cleanix/cleanixwindow.py` passa a guardar referências aos widgets que mudam e
a ligar os botões às ações reais.

### Categorias de limpeza

Todas as raízes são resolvidas com `os.path.realpath` e precisam estar dentro
de `$HOME` ou de `/tmp`.

| Categoria | Raízes | O que é apagado |
|-----------|--------|-----------------|
| Lixeira | `~/.local/share/Trash/files`, `~/.local/share/Trash/info` | conteúdo, mantendo as pastas |
| Miniaturas | `~/.cache/thumbnails` | conteúdo |
| Navegadores | `~/.cache/google-chrome`, `~/.cache/chromium`, `~/.cache/mozilla/firefox`, `~/.cache/brave-browser`, `~/.cache/microsoft-edge`, `~/.cache/vivaldi` | conteúdo das raízes existentes |
| Temporários | `/tmp` | apenas arquivos regulares do usuário, com mais de 10 minutos e que não estejam abertos por nenhum processo |

Cache do APT (`/var/cache/apt/archives`) aparece na lista como
**"Requer administrador"**, desabilitado e não contabilizado.

Regras de varredura:

- `os.walk(..., followlinks=False)`; links simbólicos são contados como item,
  mas nunca seguidos.
- Somente arquivos regulares entram no tamanho; diretórios vazios não.
- Erros de permissão são ignorados silenciosamente e contabilizados à parte.
- Arquivos abertos são detectados lendo `readlink` de `/proc/*/fd` uma única
  vez por varredura e comparando caminhos reais.
- O resultado de cada categoria é `{bytes, files, errors}`.

Regras de remoção:

- Cada caminho é revalidado no momento da exclusão (proteção contra troca de
  link entre varredura e limpeza).
- `os.unlink` para arquivos e links; diretórios só são removidos se estiverem
  dentro de uma raiz permitida e após o conteúdo ter sido removido.
- As pastas-raiz nunca são removidas.
- Falhas não interrompem o restante: são somadas em `errors` e mostradas no
  resultado.
- `os.path.commonpath` + `realpath` garantem que nada escape da raiz.

### Dados do sistema

- **Disco:** `os.statvfs('/')`; total = `f_blocks`, livre = `f_bavail`,
  usado = total − `f_bfree`. Percentual usado = (total − livre) / total.
- **Memória:** `/proc/meminfo`; usado = `MemTotal − MemAvailable`.
- **CPU:** duas leituras de `/proc/stat` com 500 ms de intervalo; percentual =
  delta ocupado / delta total. Núcleos via `os.cpu_count()`.
- **Gráfico de linha:** amostra de CPU a cada 2 s, mantendo as últimas 30
  amostras; o widget é atualizado no lugar.
- **Saúde:** livre ≥ 20% verde, 10–19% amarelo, < 10% vermelho. O texto e o
  anel mudam junto. "Última verificação" recebe a hora real da última varredura.

### Fluxo de limpeza

1. App abre e faz uma varredura inicial em segundo plano.
2. Cartão "Espaço Recuperável" mostra o total real encontrado.
3. "Ver Detalhes..." abre um diálogo modal com uma linha por categoria
   (nome, tamanho, nº de arquivos, checkbox). Categorias que exigem admin
   aparecem desabilitadas.
4. "Limpar agora" abre uma confirmação explícita com o total selecionado.
5. A limpeza roda em thread; a barra de status mostra o progresso.
6. Ao terminar, um diálogo informa bytes liberados, arquivos removidos e
   eventuais erros.
7. A tela é atualizada (disco, espaço recuperável, categorias, histórico).

Durante varredura ou limpeza, os botões de ação ficam desabilitados para evitar
duas operações concorrentes.

### Histórico

- Arquivo: `~/.local/share/cleanix/history.json`.
- Entrada: `{timestamp, bytes, files, categories: [...], errors}`.
- Máximo de 200 entradas; as mais antigas são descartadas.
- A tela mostra as 3 últimas; "Ver Histórico →" abre um diálogo com a lista
  completa e um botão para limpar o histórico.

### Interface

- Números fixos do mockup (2,48 GB, 46%, 78,4 GB, 3,1 GB, 2%, 1,02 GB etc.)
  são substituídos por valores reais formatados em pt-BR.
- A lista de categorias passa a mostrar tamanhos reais e um estado visual
  (vazio, disponível, requer admin).
- "Otimização" e "Ajustes" mostram um diálogo "Disponível em breve", sem
  simular ação.
- Nada de emojis novos; o visual do mockup é preservado.

### Erros e casos-limite

- Sem `$HOME` gravável: app abre em modo somente leitura, sem limpar.
- Navegador aberto: a limpeza é permitida, mas a confirmação avisa que o
  navegador pode recriar o cache.
- Nada encontrado: diálogo informa "Nada para limpar" e não apaga nada.
- `/proc` indisponível: CPU e arquivos abertos degradam para "indisponível",
  sem impedir o resto.

## Testes

- `unittest` (stdlib, sem dependência nova).
- `tests/test_scanner.py`: allowlist, escape por `..`, escape por symlink,
  contagem de arquivos, remoção preservando raízes, arquivo aberto ignorado.
- `tests/test_history.py`: gravação, leitura, limite de 200 entradas.
- `tests/test_systeminfo.py`: formatação e leitura de `/proc/meminfo` com
  conteúdo simulado.
- Verificação visual com capturas offscreen, como já é feito hoje.

## Riscos

- **Apagar cache com navegador aberto** pode causar recriação imediata e
  lentidão momentânea; mitigado com aviso na confirmação.
- **`/tmp` em uso** é o ponto mais sensível; mitigado pela checagem de
  arquivos abertos e pela idade mínima de 10 minutos.
- **Corrida entre varredura e limpeza** (arquivo trocado por link): mitigada
  revalidando cada caminho antes de apagar.

## Decisões deixadas para o construtor

- Textos exatos dos diálogos e do estado vazio.
- Layout interno dos diálogos (desde que use GTK4 e o CSS existente).
- Estratégia de atualização dos widgets de gráfico.
- Nomes internos de funções e classes.
