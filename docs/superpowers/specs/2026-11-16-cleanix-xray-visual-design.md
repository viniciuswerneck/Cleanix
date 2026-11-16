# Design curto — visual do Raio-X da máquina

## Intenção
Deixar o diálogo **Raio-X da máquina** com aparência de app acabado, sem mudar
o comportamento: coleta sob demanda, detalhes completos com senha, busca de
programas e exportação HTML continuam iguais.

## Abordagens consideradas
- **A) Refinar o atual:** ajustes de cor/espaçamento nos expansores nativos.
  Pouco risco, mas mudança visual discreta.
- **B) Cartões expansíveis sob medida (escolhida):** cabeçalho rico por tópico,
  resumo em cartões com ícones e contagens em badges.
- **C) Seções com barra lateral:** páginas separadas no diálogo. Visual mais
  completo, porém muda o fluxo e aumenta o escopo.

## Decisões da escolhida
- Cada tópico (BIOS, Hardware, Programas) vira um **cartão** com:
  - ícone em chip colorido;
  - título forte e uma linha de resumo sempre visível;
  - badge opcional de contagem;
  - seta que gira ao abrir;
  - corpo revelado com animação curta, dentro do próprio cartão.
- O resumo do topo vira um cartão com três linhas (BIOS, Hardware, Programas),
  cada uma com ícone, rótulo e texto.
- Cabeçalho do diálogo vira um bloco de destaque (hero) com ícone maior.
- Programas usam sub-cartões por origem (APT, Snap, Flatpak), cada um com badge
  de quantidade, busca e lista rolável. Continuam recolhidos por padrão.
- Contagens antes exibidas como número solto passam a aparecer em badges.
- Texto e cores seguem o tema escuro existente (`#17161F` / `#2B2938`).
- Nenhuma chave de comportamento, coleta ou exportação HTML é alterada.

## Fora de escopo
- Trocar o fluxo por abas/páginas.
- Alterar o conteúdo ou o layout do relatório HTML exportado.
- Novos dados coletados.
