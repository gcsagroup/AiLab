# GCSA AI Lab

[简体中文](../../README.md) · [繁體中文](../zh-TW/README.md) · [English](../en/README.md) · [日本語](../ja/README.md) · [한국어](../ko/README.md) · [Français](../fr/README.md) · [Português](README.md)

GCSA AI Lab é um aplicativo para executar modelos localmente, fazer ajuste fino com LoRA, avaliar resultados e gerenciar conteúdo gerado. Cada projeto reúne modelos, dados, tarefas e saídas para retomar o trabalho e consultar a origem dos resultados.

Versão atual: **Ver2.7 (057), prévia técnica**. O aplicativo nativo Ver2.7 (054) foi testado por túnel SSH com Qwen2.5-0.5B-Instruct: geração no Jetson Orin, treinamento LoRA de duas etapas, coleta dos resultados e execução do mesmo adaptador na GPU Apple. Essa validação se limita ao modelo e ambiente indicados e não comprova melhoria de qualidade. A implantação HTTPS direta, a instalação em ambiente limpo, os testes com novos usuários e a validação de distribuição ainda não foram concluídos. Não há instalador público validado nem canal de atualização automática. 055 corrige as mensagens de desconexão durante o envio e de estado final. Os testes nativos cobriram interrupção, verificação de estado e uma nova transferência bem-sucedida; o fluxo completo de modelos entre dispositivos de 054 não foi repetido.

056 corrige as mensagens de verificação da execução local e de ausência de mídia. O mesmo candidato assinado pela empresa concluiu dois fluxos de imagem, vídeo e voz em chinês, com reutilização explícita, alteração de entrada, recusa durante ocupação, cancelamento e nova execução após falha. Seis mídias foram exportadas separadamente e abertas em visualizadores independentes. Os 685 testes da interface passaram. Não houve treinamento. Esses resultados não comprovam a qualidade dos modelos, a validação completa de M4/M6 nem a prontidão para lançamento. 057 passa em 688 testes da interface e também corrige a navegação pelo histórico dos fluxos: tarefas com falha, em execução ou aguardando confirmação de parada exibem a execução selecionada. A verificação nativa confirmou o acesso a uma falha antiga e o retorno à etapa atual. Os dois fluxos de cálculo não foram repetidos no 057.

O trabalho continua como teste interno. As verificações adicionais de 055 cobrem restauração de backups históricos, atualização e retorno ao pacote anterior, uso independente das exportações, uma tarefa pelo teclado e a geração de mídia especificada. A revisão dos dados de negócio e os testes com cinco usuários reais continuam pendentes, sem substituição por resultados simulados.

Atualização de qualidade, 2026-10-13: o Qwen2.5-7B-Instruct existente executou uma linha de base e dois testes de prompts em 50 registros operacionais sintéticos, por inferência local independente, sem treinamento. Alguns campos melhoraram, mas permaneceram omissões de fatos e estados incorretos. O prompt revisado também seguiu uma anotação enganosa do texto original e inventou uma ação e uma recuperação. Nenhum dos prompts foi adotado. Essas amostras já foram usadas no desenvolvimento e não tiveram revisão independente de especialistas do domínio; não comprovam teste cego nem aprovação de qualidade em produção.

- Geração de texto, ajuste fino SFT + LoRA e avaliação do modelo de referência e do candidato.
- Geração de imagens e LoRA de imagem experimental, com opções de geração de vídeo, síntese de voz e transcrição. O treinamento de vídeo e áudio não está disponível.
- Importação de dados, divisão por grupo de origem, histórico, revisões de conteúdo, exportação, backup e restauração.

O suporte depende da combinação exata de modelo, dispositivo, mecanismo e precisão. Verifique a configuração antes de iniciar. Os experimentos de qualidade ainda apresentam falhas; concluir o treinamento não garante qualidade. A documentação está em sete idiomas, o que não significa que a interface ofereça todos eles.

[Guia de uso](docs/USER_GUIDE.md) · [Histórico de alterações](CHANGELOG.md) · [GitHub](https://github.com/gcsagroup/AiLab)
