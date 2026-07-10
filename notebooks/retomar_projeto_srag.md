# Prompt para retomar o projeto SRAG/SageMaker

Cole o texto abaixo numa nova conversa para retomar o projeto de onde parou.

---

Estou continuando um projeto de ML no SageMaker (notebook `aula_07_06_2023.ipynb` no SageMaker, espelhado localmente em `c:\Users\Guilherme Grandim\Desktop\Untitled.ipynb`) — classificação SRAG/COVID, target `classi_fin` (classes 1-5, SIVEP-Gripe).

**Contexto crítico:** a conta AWS não tem cota para instâncias `ml.*` de treino/endpoint (pedido de aumento negado), então todo o pipeline evita SageMaker Estimator/Endpoint: treino nativo com `xgboost` + persistência via `pickle` + inferência via AWS Lambda (sem SageMaker Endpoint).

**Limitação de ferramenta importante:** o tool `Read` não consegue abrir `Untitled.ipynb` diretamente (excede limite de tokens, ignora offset/limit em notebooks) e `NotebookEdit` não funciona por depender de um `Read` prévio bem-sucedido. Todas as edições nesse notebook devem ser feitas via scripts Python (`json.load`/mutação/`json.dump`) rodados via Bash, validando com `ast.parse` a sintaxe de células de código editadas. Use `Grep` com `-A`/`-B` pra inspecionar células.

**Estado atual do pipeline (já implementado e validado no SageMaker):**
- Split 70/15/15 treino/validação/teste, estratificado (corrigiu vazamento de teste-como-validação que existia antes)
- `classi_fin` filtrado para códigos válidos 1-5 (SIVEP-Gripe), removendo 6 (legado) e 9 (Ignorado); remapeamento 0-indexado automático via `sorted(y.unique())`
- `sample_weight` = `np.sqrt(compute_sample_weight('balanced', y_train))` — pesos totalmente balanceados sobrecorrigiam a classe 2 (rara); a raiz quadrada suavizou isso. Resultado final aprovado pelo usuário: 68% acurácia no teste real, weighted-avg F1 0.67, best_iteration 89
- `xgb.train` com `early_stopping_rounds=10`, `num_boost_round=500`
- Seção 4.7 com tabela de validação das hipóteses H1-H7 da EDA
- Modelo persistido via pickle (seção 5.5) em `/home/ec2-user/SageMaker/modelo_treinado/model.pkl`
- Todas as seções markdown renumeradas sequencialmente (5.1 a 5.7, com subseções 5.5.1 e 5.6.1-5.6.4) e todas as referências cruzadas de texto corrigidas

**Onde parei — deploy do Lambda (seção 5.6):**
- Abandonei a abordagem de Lambda Layer (zip) porque `xgboost==3.2.0` completo traz `nvidia-nccl-cu12` e passa do limite de 250MB descompactado (mesmo após strip, ficou em 723.8MB)
- Pivotei para **imagem de container via ECR** (limite de 10GB, sem esse problema) — usuário confirmou Docker funcional na instância do notebook
- Reescrevi as seções 5.6.2 (build/push da imagem Docker usando `xgboost-cpu==3.2.0` pra evitar dependências de GPU) e 5.6.3 (criação/atualização da função Lambda com `PackageType='Image'`, incluindo lógica de apagar+recriar se já existir uma função Zip antiga do fluxo `invoke_endpoint` do professor)
- Passei duas policies IAM inline para o role `FULL_SAGEMAKER`: uma com permissões de Lambda (PublishLayerVersion, funções, PassRole) e outra com permissões de ECR (CreateRepository, GetAuthorizationToken, upload de layers de imagem, PutImage etc.) + `lambda:DeleteFunction`
- **Última ação:** corrigi um erro de sintaxe JSON que o usuário levou ao colar a policy do ECR no console IAM (eu tinha mandado só o statement fragmentado, sem o wrapper `{"Version":..., "Statement":[...]}`) — mandei o documento JSON completo e pronto pra colar como nova inline policy

**Próximos passos pendentes:**
1. Confirmar que a policy IAM do ECR foi aplicada com sucesso e sem erros
2. Usuário precisa rodar no SageMaker, a partir da célula 5.6.2: criação do repo ECR, build/tag/login/push da imagem Docker, criação/atualização da função Lambda (5.6.3), e teste de invocação (5.6.4) — preciso revisar os resultados/erros que ele reportar
3. Depois do deploy funcionando ponta a ponta, atualizar a memória do projeto (`project_srag_sagemaker_pipeline.md`, que ainda descreve a abordagem antiga de Lambda Layer em alguns pontos)
4. Objetivo de longo prazo ainda não iniciado: frontend Streamlit chamando o Lambda (indeciso entre boto3 direto com credenciais locais ou exposição pública via API Gateway/Function URL)

Por favor continue direto de onde parei, sem pedir pra eu recapitular.
