# Design — Lote 6: Agendamento e lembretes (opt-in)

## Objetivo
Oferecer **lembretes** relacionados à manutenção do sistema de forma **opt-in**
(desligado por padrão), sem realizar limpezas automáticas que apaguem arquivos.

## Decisões aprovadas
- **Opt-in e padrão desligado:** nenhum agendamento/lembrete ativo até o usuário
  habilitar explicitamente em Configurações.
- **Sem limpeza automática destrutiva:** o app **não** apagará arquivos/lixo
  automaticamente em segundo plano. O lote foca em **lembrar/verificar**, não em
  executar remoções.
- **Escopo (abordagem segura, no app):** lembrete baseado no histórico/estado ao
  **abrir o aplicativo** (ou em verificação leve no arranque da UI): se faz mais
  que um intervalo escolhido desde a última limpeza/varredura registrada,
  mostrar um aviso não intrusivo com atalho para revisar/limpar. Implementação
  simples, sem serviços em segundo plano do sistema.
  - Intervalo configurável (ex.: desativado, semanal, quinzenal, mensal) nas
    Configurações.
- **Evolução possível (fora do mínimo):** agendamento via mecanismo do usuário
  (ex.: `systemd --user` timer) para abrir/notificar em horário definido pode ser
  considerado se simples e seguro, mas o lote deve entregar pelo menos o
  lembrete opt-in no app sem ações destrutivas.

## Interface
- Em **Configurações**: seção “Lembretes”/“Agendamento” com chave para ativar e
  escolha de frequência/intervalo (padrão: desativado).
- Ao iniciar/abrir, se habilitado e devido: exibir aviso/banner ou diálogo leve
  informando há quanto tempo foi a última limpeza e oferecendo ir para a área de
  limpeza (sem executar nada).

## Implementação
- Persistência da preferência em `settings` (opt-in, intervalo) e leitura da data
  da última limpeza a partir do histórico existente (`~/.local/share/cleanix/history.json`).
- Lógica pura/testável em módulo/funções (ex.: `cleanix/reminders.py` ou em
  `settings/history`): decidir se o lembrete é devido dado última limpeza,
  intervalo e data atual.
- `cleanix/dialogs.py`/`settings` UI: controles de opt-in/frequência.
- `cleanix/cleanixwindow.py` (ou ponto de arranque): checagem e exibição do
  lembrete quando aplicável.
- `cleanix/locale/{pt_BR,en,es}.json`: textos.
- `tests/test_reminders.py` (ou equivalente): devido/não devido, desativado,
  sem histórico.

## Fora de escopo (lote 6)
- Limpeza automática/remoção agendada de arquivos, execução como root em
  background, sincronização/nuvem, notificações do sistema complexas obrigatórias
  (além do aviso in-app mínimo viável).
