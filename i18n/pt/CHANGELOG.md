# Histórico de alterações

[简体中文](../../CHANGELOG.md) · [繁體中文](../zh-TW/CHANGELOG.md) · [English](../en/CHANGELOG.md) · [日本語](../ja/CHANGELOG.md) · [한국어](../ko/CHANGELOG.md) · [Français](../fr/CHANGELOG.md) · [Português](CHANGELOG.md)

2026-10-10 (atualização do código-fonte, ainda não incluída num pacote da aplicação): adicionado um ambiente fixo para Jetson Orin e corrigida a libertação da memória de trabalho CUDA. Com Qwen2.5-0.5B-Instruct, foram verificadas a geração, duas etapas de treino LoRA e o carregamento independente do mesmo adaptador exportado numa GPU Apple. Estes testes não comprovam melhoria na qualidade do modelo nem a validação do fluxo completo entre dispositivos na aplicação.

2026-10-07: documentação pública em sete idiomas, remoção dos registros internos de desenvolvimento e validação e revisão das instruções. Alteração apenas de documentação, sem recompilar o aplicativo.

## Ver2.6 (053)

Versão atual: **Ver2.6 (053), prévia técnica**. Modelos específicos foram testados para inferência e ajuste fino em Apple Silicon. Os fluxos entre NVIDIA e Apple, a instalação em ambiente limpo, os testes com novos usuários e a validação de distribuição ainda não foram concluídos. Não há instalador público validado nem canal de atualização automática.

- Mantém o foco do teclado visível após carregar outra página e preserva o indicador de conclusão na última.
- Mostra erros nos campos numéricos e recusa valores inválidos; temperatura e Top-p aceitam decimais válidos.
- Adiciona suporte experimental a um modelo 7B fixo e bloqueia combinações de cache KV quantizado 7B que falharam nos testes de qualidade.
- Oferece exportação de versões, backup, restauração, recolha de saídas e resumos de diagnóstico. A validação de distribuição e de qualidade de negócio segue incompleta.
