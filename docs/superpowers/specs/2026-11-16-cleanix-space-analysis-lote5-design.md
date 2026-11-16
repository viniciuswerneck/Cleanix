# Design — Lote 5: Análise de espaço (arquivos grandes e duplicados)

## Objetivo
Ajudar o usuário a identificar o que ocupa espaço no disco por meio de
**arquivos/pastas grandes** e **arquivos duplicados**, em modo de **revisão**
(sem apagar nada automaticamente).

## Decisões aprovadas
- **Acesso:** novo item no menu lateral **“Análise de espaço”** (seção própria,
  separada de Limpeza/Otimização).
- **Escopo:** varredura da **pasta pessoal (`$HOME`) por padrão**, com opção de
  **escolher outra pasta** (inclusive discos/pontos montados acessíveis ao
  usuário). Sem privilégios de administrador; respeita permissões do usuário.
  Ignora diretórios virtuais/especiais quando encontrados (ex.: `/proc`,
  `/sys`, `/dev`, `/run`) e não segue links simbólicos para evitar laços/saídas
  do escopo.
- **Arquivos/pastas grandes:** listar maiores itens por tamanho (arquivos; e
  pastas com tamanho agregado calculado durante a varredura) com caminho e
  tamanho legível, limitado aos principais resultados (ex.: top N).
- **Duplicados:** detecção por **conteúdo**, em etapas para desempenho:
  1. considerar arquivos regulares acima de um tamanho mínimo (ex.: 1 MiB);
  2. agrupar por tamanho;
  3. para grupos candidatos, calcular hash (SHA-256, leitura em blocos) e
     agrupar por hash. Resultado: grupos de arquivos idênticos com contagem e
     espaço desperdiçado potencial (tamanho × (cópias-1)).
- **Ação do usuário (revisão apenas):** sem apagar automaticamente e **sem
  remoção pelo app neste lote**. O usuário pode **rever** a lista e usar
  **“Abrir pasta”** (abre o local no gerenciador de arquivos / revela o item)
  para decidir fora do app. Nenhuma exclusão é executada pelo Cleanix.
- **Execução/UX:** varredura em **segundo plano**, com indicador de progresso,
  possibilidade de **cancelar**, e execução sob demanda (nada roda sozinho).

## Interface
- `SpaceAnalysisDialog` (ou equivalente) aberto pelo menu lateral “Análise de
  espaço”, com:
  - seletor/mostrador da pasta analisada (padrão `$HOME`) e botão para escolher
    outra pasta;
  - controles: iniciar/analisar e cancelar;
  - abas ou seções **“Arquivos grandes”** e **“Duplicados”** exibindo resultados
    (caminho, tamanho; grupos de duplicados com cópias e espaço recuperável por
    grupo);
  - ação por item/grupo: **Abrir pasta** (ex.: `xdg-open` da pasta/arquivo
    conforme disponível);
  - estado vazio/sem resultados e avisos quando a varredura for cancelada ou
    houver erros de permissão (relatados sem quebrar).

## Implementação
- Novo módulo `cleanix/space.py` (ou similar) com lógica pura/testável:
  - caminhada segura de diretório (sem seguir symlinks, pular especiais), coleta
    de tamanhos de arquivos e agregação por diretório;
  - seleção de maiores itens;
  - detecção de duplicados por tamanho+hash em etapas, cancelável
    (callback/flag);
  - formatação de resultados (bytes, grupos).
- `cleanix/dialogs.py` (ou módulo de UI): diálogo de análise com execução em
  thread e atualização via `GLib.idle`.
- `cleanix/cleanixwindow.py` (e/ou menu): nova entrada lateral “Análise de
  espaço”.
- `cleanix/locale/{pt_BR,en,es}.json`: textos da interface.
- `tests/test_space.py`: grandes/duplicados em diretório temporário, agrupamento
  correto, tolerância a symlinks/perm denied (simulado), e cancelamento/limites
  básicos quando aplicável.

## Fora de escopo (lote 5)
- Remoção/mover para lixeira pelo app, limpeza automática, agendamento
  (lote 6), análise com root do sistema inteiro, e comparação histórica de
  espaço.
