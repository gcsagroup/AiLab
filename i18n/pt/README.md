# GCSA AI Lab

[简体中文](../../README.md) · [繁體中文](../zh-TW/README.md) · [English](../en/README.md) · [日本語](../ja/README.md) · [한국어](../ko/README.md) · [Français](../fr/README.md) · [Português](README.md)

GCSA AI Lab é um aplicativo para executar modelos localmente, fazer ajuste fino com LoRA, avaliar resultados e gerenciar conteúdo gerado. Cada projeto reúne modelos, dados, tarefas e saídas para retomar o trabalho e consultar a origem dos resultados.

Versão atual: **Ver2.6 (053), prévia técnica**. Modelos específicos foram testados para inferência e ajuste fino em Apple Silicon. Os fluxos entre NVIDIA e Apple, a instalação em ambiente limpo, os testes com novos usuários e a validação de distribuição ainda não foram concluídos. Não há instalador público validado nem canal de atualização automática.

- Geração de texto, ajuste fino SFT + LoRA e avaliação do modelo de referência e do candidato.
- Geração de imagens e LoRA de imagem experimental, com opções de geração de vídeo, síntese de voz e transcrição. O treinamento de vídeo e áudio não está disponível.
- Importação de dados, divisão por grupo de origem, histórico, revisões de conteúdo, exportação, backup e restauração.

O suporte depende da combinação exata de modelo, dispositivo, mecanismo e precisão. Verifique a configuração antes de iniciar. Os experimentos de qualidade ainda apresentam falhas; concluir o treinamento não garante qualidade. A documentação está em sete idiomas, o que não significa que a interface ofereça todos eles.

[Guia de uso](docs/USER_GUIDE.md) · [Histórico de alterações](CHANGELOG.md) · [GitHub](https://github.com/gcsagroup/AiLab)
