# Classificador de Síndrome Respiratória Aguda Grave (SRAG/COVID-19)

![Python](https://img.shields.io/badge/python-3.11-blue?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/streamlit-1.38%2B-FF4B4B?logo=streamlit&logoColor=white)
![XGBoost](https://img.shields.io/badge/xgboost-3.2-0066CC)
![AWS Lambda](https://img.shields.io/badge/AWS-Lambda-FF9900?logo=awslambda&logoColor=white)
![License](https://img.shields.io/github/license/guigrandim/respiratory-diseases)

Frontend em Streamlit que consulta um modelo **XGBoost multiclasse**, treinado
sobre dados do **SIVEP-Gripe** (Sistema de Informação da Vigilância
Epidemiológica da Gripe, DATASUS), para sugerir a classificação final
(`classi_fin`) de um caso notificado de Síndrome Respiratória Aguda Grave a
partir de dados clínicos e de atendimento.

## Demo ao vivo

Este projeto usa *scale-to-zero* — o serviço ECS fica desligado por padrão e
acorda sozinho na primeira visita (veja a seção "Deploy" abaixo).

**Link:** https://jlqsegnebs6r6sy7sn3ebxskxy0ihkkx.lambda-url.us-east-1.on.aws/

Se o serviço estiver hibernando, a primeira visita mostra uma página de
"iniciando..." por ~1-2 minutos enquanto o ECS sobe, depois redireciona
automaticamente para o app. Esse link é permanente — não muda mais a cada
deploy.

## Destaque do projeto (modelo STAR)

**Situação**: o DATASUS disponibiliza publicamente os dados do SIVEP-Gripe
(notificações de Síndrome Respiratória Aguda Grave), mas a conta AWS usada
neste projeto não tinha cota para instâncias `ml.*` do SageMaker — o caminho
"padrão" de treinar/servir via SageMaker Estimator/Endpoint gerenciado estava
descartado.

**Tarefa**: construir, do zero, um classificador multiclasse (5 classes de
`classi_fin`) com uma aplicação usável ponta a ponta — treino, empacotamento
do modelo, serviço de inferência e frontend — hospedada na AWS, gastando o
mínimo possível de recurso, já que é um projeto de portfólio sem tráfego
constante.

**Ação**:
- Engenharia de features (faixa etária, score de comorbidades, macro-região,
  sazonalidade via seno/cosseno da semana epidemiológica, score vacinal) e
  treino de um XGBoost nativo (early stopping, pesos de amostra balanceados)
  direto no notebook, sem depender do Estimator gerenciado do SageMaker.
- Contornei a falta de cota de endpoint gerenciado empacotando o modelo
  (`pickle`) e servindo via uma AWS Lambda em container (Docker + ECR), com o
  `objective` ajustado para `multi:softprob` **sem retreino** para expor a
  confiança por classe, não só o rótulo vencedor.
- Investiguei a procedência de uma feature crítica não documentada
  oficialmente (`delta_uti`, a de maior peso no modelo treinado) cruzando o
  dicionário oficial de dados do SIVEP-Gripe, o catálogo Glue/Athena da
  tabela de origem e uma consulta agregada no Athena — documentando a
  limitação encontrada em vez de ocultá-la.
- Construí um frontend Streamlit (página de apresentação + formulário) que
  invoca a Lambda via `boto3`, containerizei com Docker e implantei em ECS
  Fargate.
- Reduzi o custo de infraestrutura a zero quando ocioso: o serviço fica com
  `desiredCount=0` por padrão, com scripts de start/stop e uma Lambda de
  auto-stop (via EventBridge) que desliga o serviço automaticamente após um
  limite de tempo de uptime.
- Revisei o código com um agente independente antes de ir para produção,
  corrigindo dependências não usadas e uma imagem-base desatualizada no
  Dockerfile.

**Resultado**: modelo com **68% de acurácia** e **F1 ponderado de 0.67** no
conjunto de teste (nunca visto durante o treino/early stopping); pipeline
completo em produção na AWS (Streamlit → Lambda → XGBoost) com custo de
infraestrutura efetivamente zero quando não está em uso; limitações
conhecidas documentadas de forma transparente em vez de escondidas.

## Arquitetura

![Diagrama de arquitetura: SIVEP-Gripe/DATASUS → S3 → Glue Catalog → S3 (train.parquet) → Notebook SageMaker (feature engineering + treino XGBoost) → model.pkl (S3); Formulário Streamlit → ECS Fargate → AWS Lambda → model.pkl](assets/img/arquitetura.png)

- A tabela de origem (`database_health_bridge.table_train_gg_solutionstrain`,
  Glue Catalog) é o dado histórico do SIVEP-Gripe já catalogado; o Athena é
  usado tanto para materializar o `train.parquet` consumido pelo notebook
  quanto para consultas ad-hoc de investigação (ex.: a distribuição do
  `delta_uti`, ver ressalva abaixo).
- O treino (split, feature engineering, XGBoost, avaliação) roda inteiramente
  no notebook `notebooks/training_pipeline.ipynb` (fonte da verdade, espelha o que
  roda no SageMaker) e persiste o modelo via `pickle`.
- A inferência não usa SageMaker Endpoint (conta sem cota para instâncias
  `ml.*`): o Streamlit invoca diretamente uma função Lambda via `boto3`, que
  carrega o `model.pkl` do S3 e roda `booster.predict`.
- O modelo usa `objective='multi:softprob'`, retornando a probabilidade das 5
  classes por caso (não apenas o rótulo vencedor).
- O Streamlit roda em ECS Fargate sob demanda (ver seção "Deploy" abaixo),
  não como servidor sempre ligado.

## Rodando localmente

```bash
pip install -r requirements.txt
streamlit run home.py
```

Requer credenciais AWS configuradas (`~/.aws/credentials`) com permissão de
`lambda:InvokeFunction` na função configurada em `LAMBDA_FUNCTION_NAME`
(variável de ambiente, default `requisicoes_ml_sagemaker`).

## Docker

```bash
docker build -t respiratory-diseases-app .
docker run -p 8501:8501 -v ~/.aws:/root/.aws:ro respiratory-diseases-app
```

## Deploy (ECS Fargate) — liga sozinho sob demanda

O app roda em um serviço ECS Fargate (`respiratory-diseases-cluster` /
`respiratory-diseases-task-service-l0kgkxxb`), mas **fica parado por padrão**
(`desiredCount=0`) para não gerar custo continuo — é um projeto de
portfólio, sem tráfego constante.

- **Ligar**: automático. Uma Lambda pública ("porteira",
  `respiratory-diseases-wake`, código em `scripts/lambda_wake/`) é o link
  fixo do projeto. Ao receber uma requisição, ela confere o estado do
  serviço ECS; se estiver parado, chama `ecs:UpdateService` para subir e
  devolve uma página HTML que se auto-atualiza a cada ~10s; quando a task
  está `RUNNING` e passou de uma janela de warm-up, devolve um redirect 302
  direto para o IP público da task (`http://<ip>:8501`) — dali em diante o
  navegador fala direto com o Fargate, sem a Lambda no meio, então o
  WebSocket do Streamlit funciona normalmente.
- **Desligar na hora**: `scripts/parar_app.sh`.
- **Auto-stop**: uma função Lambda (`respiratory-diseases-auto-stop`),
  disparada a cada 10 minutos por uma regra do EventBridge, derruba o
  serviço automaticamente depois de 2h de uptime (`MAX_UPTIME_MINUTES`, env
  var da Lambda) — não é detecção de tráfego, é um limite de tempo de
  sessão.
- Nenhum ALB/NLB é usado (custo fixo extra não valeria a pena para o volume
  de tráfego deste projeto) — a porteira usa só a Function URL nativa da
  Lambda.

## Ressalva conhecida: `delta_uti`

`delta_uti` é a feature de **maior peso** no modelo treinado (maior
`gain`/`total_gain`/`cover` das 11 features usadas), mas o nome não existe no
dicionário oficial de dados do SIVEP-Gripe (conferido no PDF oficial de
19/09/2022, opendatasus.saude.gov.br). A leitura de trabalho da equipe é que
se trata de um valor calculado a partir dos campos oficiais **54 - Data de
entrada na UTI** (`DT_ENTUTI`) e **55 - Data de saída da UTI** (`DT_SAIDUTI`)
— consistente com a distribuição observada dos valores (via consulta Athena),
mas **não é uma definição publicada pelo DATASUS** com esse nome. Antes de
usar este modelo em um contexto clínico real, vale confirmar a definição
exata com quem construiu o pipeline de dados de origem.

## Estrutura do repositório

- `home.py` — página inicial: visão geral do projeto e dicionário de campos.
- `pages/1_Formulario.py` — formulário de entrada e exibição da previsão.
- `common.py` — constantes e lógica compartilhada (mapeamento de labels,
  cálculo de features derivadas, invocação da Lambda).
- `notebooks/training_pipeline.ipynb` — notebook de treino (fonte da verdade).
- `scripts/lambda_wake/` — código da Lambda "porteira" que liga o ECS sob
  demanda e serve como link fixo do projeto (ver seção "Deploy").
- `scripts/parar_app.sh` — desliga o serviço ECS manualmente.
- `assets/` — ficha oficial de notificação do SIVEP-Gripe (PDF), usada como
  referência para os códigos dos campos do formulário.
- `assets/img/arquitetura.png` — diagrama da arquitetura usado na seção acima.

## Licença

Distribuído sob a licença MIT — veja [LICENSE](LICENSE).
