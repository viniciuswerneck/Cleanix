# Plano de melhoria completo — Cleanix

> Execução incremental: implementar por fases (1 → 2 → 3), com testes/checks e commits.

## Fase 1
- [x] 1.1 Análise de espaço: progresso/etapas, contagem e resultado parcial ao cancelar
- [x] 1.2 Análise de espaço: exclusões de pastas e filtros (tamanho mínimo)
- [ ] 1.3 Responsividade/consistência visual em telas densas (Otimização, Raio-X, Análise, diálogos) — **parcial**: Otimização e contêiner rolável na Análise de espaço; falta revisar Raio-X/demais diálogos e telas pequenas
- [x] 1.4 Mensagens/estados vazios e erros mais claros (ferramentas ausentes/indisponível, o que fazer)
- [x] 1.5 Documentação: “o que é seguro limpar” e troubleshooting no README/ajuda

## Fase 2
- [x] 2.1 Análise de espaço: mover para Lixeira com seleção, prévia e confirmação (duplicados: escolher cópia a manter)
- [ ] 2.4 Acessibilidade básica: foco/teclado e rótulos nos controles principais
- [ ] 2.2 Lembretes: opção de notificação/agendamento do usuário (opt-in) sem limpeza automática
- [ ] 2.3 Cobertura segura adicional (categorias/ações de baixo risco, com prévia)

## Fase 3
- [ ] 3.1 Empacotamento: metadados AppStream, manifesto Flatpak (esqueleto), revisão desktop/install — **parcial**: adicionados `data/br.cleanix.Cleanix.metainfo.xml` e `flatpak/br.cleanix.Cleanix.yml` (esqueleto); falta validar build/permissões sandbox e fluxo de release
- [ ] 3.2 Desempenho: ajustes na análise de espaço para pastas grandes
- [ ] 3.3 Qualidade: ampliar testes em bordas críticas

## Estado salvo (para continuar depois)
- **Branch:** `feat/funcionalidades-reais` (sincronizado com `origin` no último push).
- **Última verificação:** `python3 -m unittest discover -s tests` → **201 testes OK**.
- **Principais entregas recentes:** análise de espaço com progresso/resultado parcial, exclusões e filtro de tamanho, mover selecionados para Lixeira com prévia/confirmação e regra de manter cópia em duplicados; docs de limpeza segura/troubleshooting; esqueleto AppStream/Flatpak.
- **Arquivos-chave:** `cleanix/space.py`, `cleanix/dialogs.py` (`SpaceAnalysisDialog`), `tests/test_space.py`, `README.md`, `data/br.cleanix.Cleanix.metainfo.xml`, `flatpak/br.cleanix.Cleanix.yml`.
- **Próximos passos sugeridos:** retomar por **2.4** (acessibilidade básica: foco/teclado/rótulos) e completar **1.3** (responsividade em Raio-X e demais diálogos), depois **3.1** (validar Flatpak), **3.2** (desempenho em pastas grandes), **2.2/2.3** e **3.3** conforme prioridade.
- **Lembrete:** manter princípios — nada apaga automaticamente; remoções só com seleção/prévia/confirmação; redigir identificadores por padrão nos exports/snapshots.
