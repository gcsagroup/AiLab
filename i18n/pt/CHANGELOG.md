# Histórico de alterações

[简体中文](../../CHANGELOG.md) · [繁體中文](../zh-TW/CHANGELOG.md) · [English](../en/CHANGELOG.md) · [日本語](../ja/CHANGELOG.md) · [한국어](../ko/CHANGELOG.md) · [Français](../fr/CHANGELOG.md) · [Português](CHANGELOG.md)

## 2026-10-13 · Registros de qualidade e manutenção dos testes

Atualização de qualidade, 2026-10-13: o Qwen2.5-7B-Instruct existente executou uma linha de base e dois testes de prompts em 50 registros operacionais sintéticos, por inferência local independente, sem treinamento. Alguns campos melhoraram, mas permaneceram omissões de fatos e estados incorretos. O prompt revisado também seguiu uma anotação enganosa do texto original e inventou uma ação e uma recuperação. Nenhum dos prompts foi adotado. Essas amostras já foram usadas no desenvolvimento e não tiveram revisão independente de especialistas do domínio; não comprovam teste cego nem aprovação de qualidade em produção.

Foram documentadas as falhas dos testes independentes de prompts 7B; nenhum prompt se tornou padrão do aplicativo. O teste de nova tentativa do mercado de dados passou a esperar o botão de download antes de interagir. Apenas os testes e a documentação mudaram; o App não foi recompilado e o candidato assinado continua sendo Ver2.7 (055). A qualidade completa, os testes com cinco usuários reais e a aceitação da distribuição continuam pendentes.

## Ver2.7 (055) · 2026-10-10

Corrigida a identificação incorreta de desconexões durante o envio remoto como falhas do serviço de controle. A causa real é preservada e a verificação de estado não reenvia o cálculo. O teste nativo confirmou interrupção, verificação de estado, reconexão e uma nova transferência bem-sucedida, com conteúdo idêntico no arquivo recebido e preservação do registro original.

055 corrige as mensagens de desconexão durante o envio e de estado final. Os testes nativos cobriram interrupção, verificação de estado e uma nova transferência bem-sucedida; o fluxo completo de modelos entre dispositivos de 054 não foi repetido.

Verificação adicional de 055: o mesmo adaptador experimental treinado anteriormente no AGX foi exportado pela interface nativa e carregado independentemente de uma cópia com o ambiente MLX incluído, na GPU Apple. A geração foi concluída, o hash correspondeu, o modelo base e os arquivos exportados permaneceram inalterados e o processo terminou naturalmente. Não houve novo treinamento; a aprovação de qualidade e a validação completa de distribuição entre dispositivos continuam pendentes.

Verificações adicionais do teste interno aprovadas: restauração de backup histórico, reversão de migração com falha, atualização 054→055 e retorno ao pacote anterior. Foram verificados os 64 arquivos de conteúdo de doze tipos de exportação após a restauração; modelos base e quantizados e adaptadores de texto e imagem foram carregados de cópias independentes. Também foram verificados uma tarefa nativa pelo teclado, geração de imagem, vídeo e voz com o pacote atual e cancelamento após o início do cálculo real. Isso não comprova qualidade dos modelos, aprovação de instalação limpa ou prontidão para lançamento oficial.

## Ver2.7 (054) · 2026-10-10

Versão atual: **Ver2.7 (054), prévia técnica**. O aplicativo nativo foi testado por túnel SSH com Qwen2.5-0.5B-Instruct: geração no Jetson Orin, treinamento LoRA de duas etapas, coleta dos resultados e execução do mesmo adaptador na GPU Apple. Essa validação se limita ao modelo e ambiente indicados e não comprova melhoria de qualidade. A implantação HTTPS direta, a instalação em ambiente limpo, os testes com novos usuários e a validação de distribuição ainda não foram concluídos. Não há instalador público validado nem canal de atualização automática.

2026-10-07: documentação pública em sete idiomas, remoção dos registros internos de desenvolvimento e validação e revisão das instruções. Alteração apenas de documentação, sem recompilar o aplicativo.

## Ver2.6 (053)

Versão atual: **Ver2.6 (053), prévia técnica**. Modelos específicos foram testados para inferência e ajuste fino em Apple Silicon. Os fluxos entre NVIDIA e Apple, a instalação em ambiente limpo, os testes com novos usuários e a validação de distribuição ainda não foram concluídos. Não há instalador público validado nem canal de atualização automática.

- Mantém o foco do teclado visível após carregar outra página e preserva o indicador de conclusão na última.
- Mostra erros nos campos numéricos e recusa valores inválidos; temperatura e Top-p aceitam decimais válidos.
- Adiciona suporte experimental a um modelo 7B fixo e bloqueia combinações de cache KV quantizado 7B que falharam nos testes de qualidade.
- Oferece exportação de versões, backup, restauração, recolha de saídas e resumos de diagnóstico. A validação de distribuição e de qualidade de negócio segue incompleta.
