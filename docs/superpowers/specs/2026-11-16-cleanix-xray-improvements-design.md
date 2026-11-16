# Design — melhorias do Raio-X (privacidade, conteúdo e relatório)

## Intenção
Evoluir o **Raio-X da máquina** e o relatório HTML para serem mais seguros,
completos, traduzidos e úteis, mantendo o fluxo atual (coleta sob demanda,
senha apenas para detalhes completos e abertura automática do relatório).

## Escopo aprovado

### 1. Privacidade no relatório
- O relatório ganha a opção **“Ocultar números de série e identificadores”**,
  marcada por padrão no diálogo.
- Quando ativa, remove/mascara valores de `Serial Number`, `UUID`, `SKU Number`
  e `Asset Tag` do `dmidecode`, e `serial:` do `lshw`.
- O HTML mostra uma linha discreta informando que os identificadores foram
  ocultados.

### 2. Tradução dos detalhes
- Todos os rótulos fixos em português no `xray.py` passam pelo catálogo i18n
  (seções, campos de BIOS, CPU/memória/discos, mensagens de erro).
- Vale para pt-BR, inglês e espanhol.

### 3. Ações e acabamento do HTML
- Botão **Imprimir / PDF**, botão **Voltar ao topo** e alternância
  **claro/escuro** (lembrada no navegador).
- Rodapé com versão do Cleanix e data de geração.
- Tema escuro usa as mesmas variáveis de cor do claro.

### 4. Programas mais úteis
- Cada programa passa a carregar **tamanho** quando disponível:
  APT (`Installed-Size` do dpkg) e Flatpak (`size`); Snap fica sem tamanho.
- O diálogo ganha **busca única** que filtra as três origens ao mesmo tempo.
- Cada origem ganha botão **“Mostrar todos”** quando a lista filtrada passa do
  limite de 500 itens.
- O HTML ganha coluna **Tamanho** e cabeçalhos **ordenáveis** por nome/versão.
- Data de instalação não é incluída (não há fonte confiável e barata para as
  três origens).

### 5. Atualização visível
- O diálogo mostra **“Atualizado às HH:MM”** após cada coleta.
- Um botão **Atualizar** também fica no rodapé, sempre visível.

### 6. Destaques e alertas
- O resumo passa a mostrar **destaques** calculados localmente:
  - BIOS com mais de 6 anos;
  - partição com uso ≥ 90%;
  - 20 ou mais runtimes Flatpak;
  - atualizações APT pendentes (contagem via `apt list --upgradable`).
- Alertas aparecem no diálogo (linha destacada) e no HTML (cartão “Destaques”).

### 7. Novas seções
- **Rede**: interfaces físicas (exceto `lo`), estado, IPv4/IPv6 e MAC.
  O MAC é ocultado quando a opção de privacidade está ativa.
- **Sistema**: uptime, atualizações pendentes, Secure Boot e presença de TPM.
- **Discos** no HTML: tabela com disco/partição, tipo, total, usado, % e ponto
  de montagem, a partir da varredura já usada na tela inicial.
- Essas seções entram no diálogo como novos cartões e no HTML com âncoras.

### 8. Acabamentos de UX
- Botões **Copiar** para os detalhes de BIOS, hardware, rede e sistema.
- **Expandir tudo / Recolher tudo** no diálogo.
- Indicador de atividade (spinner) no cabeçalho durante a coleta.
- `Esc` fecha o diálogo.

## Decisões
- A opção de privacidade vale por exportação (marcada por padrão); não é
  persistida em configurações nesta rodada.
- Alertas são calculados sem privilégios e sem rede.
- O relatório continua **autocontido** (CSS/JS embutidos) e pronto para
  impressão/PDF.
- A montagem do HTML permanece em `xray.build_report_html`, agora recebendo
  também rede, sistema, discos, alertas e a opção de ocultar identificadores.
- As novas coletas rodam junto da coleta sem privilégios já existente, em
  thread, para não travar a interface.

## Fora de escopo
- SMART dentro do Raio-X/relatório (continua no diálogo de saúde dos discos).
- Data de instalação de programas.
- Persistir preferências do relatório entre sessões.
- Alterar o fluxo de senha única já existente.

## Riscos e cuidados
- Saída de `dmidecode`/`lshw` pode variar entre máquinas: o mascaramento deve
  ser tolerante a formatos e nunca quebrar o relatório.
- `apt list --upgradable` pode demorar; roda em thread e tem timeout curto.
- Nomes de interfaces e IPs são dados sensíveis: também passam pelo
  mascaramento de MAC, mas IPs permanecem (úteis no diagnóstico).
- O relatório precisa continuar escapando todo conteúdo vindo do sistema.
