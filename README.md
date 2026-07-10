# Classificador de Síndrome Respiratória Aguda Grave (SRAG/COVID-19)

Frontend em Streamlit que consulta um modelo **XGBoost multiclasse**, treinado
sobre dados do **SIVEP-Gripe** (Sistema de Informação da Vigilância
Epidemiológica da Gripe, DATASUS), para sugerir a classificação final
(`classi_fin`) de um caso notificado de Síndrome Respiratória Aguda Grave a
partir de dados clínicos e de atendimento.

## Arquitetura

```
Streamlit (home.py + pages/1_Formulario.py)
        │  boto3 invoke (RequestResponse)
        ▼
AWS Lambda (container image, xgboost-cpu)
        │  s3.download_file
        ▼
model.pkl (S3) — Booster treinado no notebook SageMaker (notebooks/Untitled.ipynb)
```

- O treino (split, feature engineering, XGBoost, avaliação) roda inteiramente
  no notebook `notebooks/Untitled.ipynb` (fonte da verdade, espelha o que
  roda no SageMaker) e persiste o modelo via `pickle`.
- A inferência não usa SageMaker Endpoint (conta sem cota para instâncias
  `ml.*`): o Streamlit invoca diretamente uma função Lambda via `boto3`, que
  carrega o `model.pkl` do S3 e roda `booster.predict`.
- O modelo usa `objective='multi:softprob'`, retornando a probabilidade das 5
  classes por caso (não apenas o rótulo vencedor).

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

## Deploy (ECS Fargate) — liga sob demanda

O app roda em um serviço ECS Fargate (`respiratory-diseases-cluster` /
`respiratory-diseases-task-service-l0kgkxxb`), mas **fica parado por padrão**
(`desiredCount=0`) para não gerar custo continuo — é um projeto de
portfólio, sem tráfego constante.

- **Ligar**: `scripts/iniciar_app.sh` — sobe o serviço, espera a task ficar
  saudável e imprime o link público (IP direto, sem load balancer — muda a
  cada start).
- **Desligar na hora**: `scripts/parar_app.sh`.
- **Auto-stop**: uma função Lambda (`respiratory-diseases-auto-stop`),
  disparada a cada 10 minutos por uma regra do EventBridge, derruba o
  serviço automaticamente depois de 2h de uptime (`MAX_UPTIME_MINUTES`, env
  var da Lambda) — não é detecção de tráfego (o serviço não tem load
  balancer para medir requisições), é um limite de tempo de sessão. Ambos os
  scripts e a Lambda usam apenas `ecs:UpdateService` na task definition e no
  serviço já existentes; nenhuma outra configuração (porta, imagem, roles do
  container) muda.

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
- `notebooks/Untitled.ipynb` — notebook de treino (fonte da verdade).
- `assets/` — ficha oficial de notificação do SIVEP-Gripe (PDF), usada como
  referência para os códigos dos campos do formulário.
