# Guia de uso

[简体中文](../../../docs/USER_GUIDE.md) · [繁體中文](../../zh-TW/docs/USER_GUIDE.md) · [English](../../en/docs/USER_GUIDE.md) · [日本語](../../ja/docs/USER_GUIDE.md) · [한국어](../../ko/docs/USER_GUIDE.md) · [Français](../../fr/docs/USER_GUIDE.md) · [Português](USER_GUIDE.md)

Versão atual: **Ver2.7 (057), prévia técnica**. O aplicativo nativo Ver2.7 (054) foi testado por túnel SSH com Qwen2.5-0.5B-Instruct: geração no Jetson Orin, treinamento LoRA de duas etapas, coleta dos resultados e execução do mesmo adaptador na GPU Apple. Essa validação se limita ao modelo e ambiente indicados e não comprova melhoria de qualidade. A implantação HTTPS direta, a instalação em ambiente limpo, os testes com novos usuários e a validação de distribuição ainda não foram concluídos. Não há instalador público validado nem canal de atualização automática. 055 corrige as mensagens de desconexão durante o envio e de estado final. Os testes nativos cobriram interrupção, verificação de estado e uma nova transferência bem-sucedida; o fluxo completo de modelos entre dispositivos de 054 não foi repetido.

056 corrige as mensagens de verificação da execução local e de ausência de mídia. O mesmo candidato assinado pela empresa concluiu dois fluxos de imagem, vídeo e voz em chinês, com reutilização explícita, alteração de entrada, recusa durante ocupação, cancelamento e nova execução após falha. Seis mídias foram exportadas separadamente e abertas em visualizadores independentes. Os 685 testes da interface passaram. Não houve treinamento. Esses resultados não comprovam a qualidade dos modelos, a validação completa de M4/M6 nem a prontidão para lançamento. 057 passa em 688 testes da interface e também corrige a navegação pelo histórico dos fluxos: tarefas com falha, em execução ou aguardando confirmação de parada exibem a execução selecionada. A verificação nativa confirmou o acesso a uma falha antiga e o retorno à etapa atual. Os dois fluxos de cálculo não foram repetidos no 057.

O trabalho continua como teste interno. As verificações adicionais de 055 cobrem restauração de backups históricos, atualização e retorno ao pacote anterior, uso independente das exportações, uma tarefa pelo teclado e a geração de mídia especificada. A revisão dos dados de negócio e os testes com cinco usuários reais continuam pendentes, sem substituição por resultados simulados.

O suporte depende da combinação exata de modelo, dispositivo, mecanismo e precisão. Verifique a configuração antes de iniciar. Os experimentos de qualidade ainda apresentam falhas; concluir o treinamento não garante qualidade. A documentação está em sete idiomas, o que não significa que a interface ofereça todos eles.

## Escopo atual de validação (2026-10-13)

| Uso | Combinação com evidência em hardware real | Limites |
| --- | --- | --- |
| Texto local | Qwen2.5-0.5B-Instruct · MLX · Apple GPU | Geração, SFT + LoRA, recuperação e exportação têm evidência técnica; a qualidade de treinamento e quantização ainda apresenta falhas. |
| Texto remoto | Qwen2.5-0.5B-Instruct · Jetson Orin · túnel SSH | 054 verificou o retorno do mesmo LoRA ao Apple; 055 acrescentou recuperação de upload e carregamento após exportação, sem repetir toda a cadeia entre dispositivos. |
| Imagens | Tiny-SD · Diffusers / MPS · 512×512 | Geração e LoRA de imagens são experimentais, com problemas estruturais conhecidos. |
| Vídeo | SVD imagem para vídeo · 14 quadros · 7 FPS | Há evidência de execução de clipes de cerca de 2 segundos; a qualidade do movimento permanece limitada. Treinamento de vídeo está fora do escopo. |
| Voz | Kokoro-82M · voz chinesa Xiaobei · CPU · 24 kHz WAV | Arquivos de voz foram gerados; a avaliação auditiva humana continua incompleta. |
| Quantização de pesos | Qwen2.5-0.5B-Instruct · MLX 4-bit / group 64 / affine | Conversão, carregamento e exportação têm evidência; candidatos que falham nos critérios de qualidade não podem ser registrados como aprovados. |

A tabela lista apenas combinações fixas com evidência, sem garantir compatibilidade de modelos relacionados, outras precisões ou dispositivos. ASR, treinamento de áudio/vídeo, mesclagem, destilação, decodificação especulativa, Core ML/ANE e extensões AMD/Intel estão fora do escopo aceito. Uma entrada na interface ou dependência instalada não comprova disponibilidade. Nenhum candidato a entrega passou pela validação independente de qualidade de negócio.

## 1. Primeiro resultado

Crie um projeto no aplicativo com o ambiente de execução já preparado e escolha a geração de texto. Para preparar um modelo oficial, consulte a origem, a licença e a lista de arquivos. Após o download, adicione-o à biblioteca do projeto. Também é possível importar uma pasta local completa. Selecione o modelo, informe o texto e verifique a configuração antes de executar. Salve o resultado para encontrá-lo na biblioteca de conteúdo. Baixar, importar e salvar rascunhos não executa o modelo.

## 2. Tarefas e parâmetros

Retome tarefas pela área de trabalho ou pela fila. Rascunhos são salvos automaticamente; se houver falha, tente novamente e confirme o salvamento. Resultados anteriores mantêm o modelo e os parâmetros originais. Confira as diferenças de uma predefinição antes de aplicá-la e faça nova verificação. Os parâmetros incluem limite de saída, temperatura, Top-p, semente, orçamento de contexto, sequências de parada e exibição progressiva. O orçamento inclui o modelo de mensagem, a entrada e a saída reservada; solicitações acima do limite são recusadas. Use uma sequência de parada por linha, até 8 com 128 caracteres cada. A opção de pouca memória pode ser mais lenta. O cache KV de 4-bit está bloqueado e é diferente da quantização dos pesos. Carregue tarefas antigas no final da lista; a última página mantém o indicador de conclusão.

Blocos menores de prompt não garantem maior velocidade e podem alterar a saída. Para reproduzir um resultado, mantenha fixos o limite do bloco, o modelo, a precisão, os parâmetros de amostragem e a semente.

## 3. Treinamento e dados

O ajuste de linguagem usa uma receita fixa SFT + LoRA; LoRA de imagem é experimental. Confira o formato e as amostras supervisionadas válidas. Divida treino e validação por grupo de origem para evitar vazamento, visualize a divisão e aplique-a; os originais permanecem. Mudanças nos dados, no modelo ou nos parâmetros exigem nova verificação. Fixe o plano de avaliação antes do treino e mantenha suas amostras separadas. Compare o modelo base com o adaptador. Resultados abaixo dos critérios continuam experimentais e não podem ser registrados como candidatos aprovados. Pausa e retomada dependem da confirmação na interface e dos checkpoints disponíveis.

Atualização de qualidade, 2026-10-13: o Qwen2.5-7B-Instruct existente executou uma linha de base e dois testes de prompts em 50 registros operacionais sintéticos, por inferência local independente, sem treinamento. Alguns campos melhoraram, mas permaneceram omissões de fatos e estados incorretos. O prompt revisado também seguiu uma anotação enganosa do texto original e inventou uma ação e uma recuperação. Nenhum dos prompts foi adotado. Essas amostras já foram usadas no desenvolvimento e não tiveram revisão independente de especialistas do domínio; não comprovam teste cego nem aprovação de qualidade em produção.

Um JSON válido não garante a exatidão dos fatos de um registro de negócio. Confira separadamente serviços e nós, horários, ações executadas, atualizações posteriores e evidências de recuperação. Sugestões, negações e anotações em forma de instrução no original não devem se tornar ações realizadas. Os testes sintéticos de 2026-10-13 não atenderam aos critérios de adoção e suas saídas ainda precisam de revisão humana; não constituem aceitação de qualidade do App nativo.

## 4. Fluxos de mídia

O escopo atual de mídia cobre geração de imagens, vídeos curtos e voz com os modelos e ambientes indicados acima. O fluxo imagem → vídeo → voz preserva entradas e resultados de cada etapa. Alterar uma entrada anterior marca os resultados seguintes como desatualizados. Selecione a reutilização explicitamente; ela não representa uma nova geração. As amostras atuais têm limitações de qualidade: confira imagens, som e vídeo.

## 5. Revisões e exportação

Texto e roteiro de voz aceitam até 16000 caracteres cada. Legendas aceitam 200 entradas, 16000 caracteres no total e 500 por entrada. Os tempos são em segundos, ordenados, sem sobreposição e dentro da duração original. Editar texto não altera os parâmetros de geração; editar o roteiro não sintetiza novo áudio. As legendas são arquivos VTT separados, sem gravação na imagem do vídeo. Selecione o original ou uma revisão específica antes de exportar; a ação de exportar o original no cartão sempre usa o original. Escolha a pasta e confira o escopo. A exportação termina somente após gravar e verificar todos os arquivos. Pacotes de adaptadores identificam o modelo base exato, mas não incluem seus pesos por padrão. A exportação de dados divididos inclui texto original e identificadores de origem; confira o escopo.

## 6. Mercado de dados e ajuda de IA

Baixe conforme as condições do fornecedor. A aprovação não substitui a verificação dos arquivos nem a licença de uso. Versões completamente baixadas podem ser verificadas e importadas pela lista local e depois selecionadas explicitamente para a tarefa. A integração completa com mercados comerciais não foi validada. A ajuda de IA mostra sugestões e diferenças; você decide se quer aplicá-las. Aplicar uma sugestão não executa a tarefa.

## 7. Backup e restauração

Crie um backup completo nas configurações de dispositivo e ambiente, depois de resolver tarefas em execução, downloads e paradas não confirmadas. O backup inclui o banco de dados e os arquivos referenciados; modelos grandes exigem espaço extra. Restaure em uma nova pasta e depois escolha explicitamente essa biblioteca. A original permanece. Uma cópia de migração apenas do banco não é um backup completo. Aplicativos antigos podem não ler bibliotecas novas; para voltar, use uma biblioteca compatível e o backup anterior à atualização. A limpeza mostra o escopo, trata apenas arquivos sem referência na biblioteca atual e oferece restauração.

## 8. Execução remota

Cadastre o endereço do serviço, o ID do executor e as credenciais. O certificado HTTPS deve ser válido e corresponder ao host. A conexão não comprova que GPU ou modelo estejam prontos. O destino padrão do projeto afeta somente novas tarefas de texto; rascunhos existentes mantêm seu destino. Confira o destino, os arquivos e o tamanho total antes de confirmar o envio. A verificação de configuração não faz upload. O aplicativo nativo guarda credenciais no chaveiro do sistema; o navegador de desenvolvimento as mantém apenas na sessão atual do serviço de controle. O fluxo Jetson Orin indicado foi testado por túnel SSH: geração, treinamento, coleta, salvamento do adaptador experimental e seleção da GPU Apple local para teste. A implantação HTTPS direta ainda não foi validada; duas etapas de treinamento comprovam apenas o funcionamento do fluxo.

## 9. Solução de problemas

Após uma interrupção, reconecte e verifique a tarefa original. Uma desconexão não confirma a parada remota; não inicie outra execução. Se o cálculo terminou e só a transferência falhou, recolha as saídas existentes sem recalcular. Pastas parciais de exportações com falha ou canceladas não são pacotes completos. Confira o resumo de diagnóstico nas configurações antes de salvar. Ele exclui o texto das tarefas, logs brutos, credenciais e caminhos locais. Ao relatar um problema, informe versão, passos para reproduzir e diagnósticos revisados, sem dados privados.

[GCSA AI Lab](../README.md)
