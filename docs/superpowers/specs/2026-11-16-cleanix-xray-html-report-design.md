# Design curto — relatório HTML completo do Raio-X

## Intenção
Gerar um relatório HTML com **todos** os dados do Raio-X, inclusive os que
dependem de senha de administrador, e com aparência de relatório profissional.

## Abordagens consideradas
- **A) Relatório claro e profissional (escolhida):** layout de documento com
  cabeçalho em destaque, cartões de resumo, seções e tabelas. Bom na tela e na
  impressão/PDF.
- **B) Relatório escuro:** mesmo conteúdo com o tema do app; menos adequado
  para imprimir.

## Decisões
- Ao clicar em **Gerar HTML**, se os detalhes completos ainda não estiverem em
  memória, o app pede a senha **uma única vez** e executa `dmidecode` e `lshw`
  no mesmo comando privilegiado. O relatório só é gravado depois da coleta.
- Se a senha for cancelada ou a coleta falhar, o relatório **ainda é gerado**
  com os dados básicos e um aviso visível de que os detalhes completos não
  foram incluídos.
- O HTML é autocontido (CSS e JS embutidos), sem depender de internet:
  - cabeçalho com produto, sistema e data de geração;
  - navegação por âncoras (Resumo, BIOS, Hardware, Programas);
  - cartões de resumo;
  - BIOS e Hardware com os detalhes completos e a origem indicada;
  - Programas em tabelas por origem (APT, Snap, Flatpak), com contagem e busca;
  - lista de observações/limitações quando existirem;
  - estilos de impressão (sem sombras, tabelas expandidas).
- A montagem do HTML sai do diálogo e vira função pura em `cleanix/xray.py`
  (`build_report_html`), testável sem GTK.
- Conteúdo é escapado para evitar HTML injetado por nomes de pacotes.

## Fora de escopo
- Incluir SMART/discos no relatório (o Raio-X não cobre essa seção).
- Alterar a coleta normal do diálogo ou a verificação SMART.
