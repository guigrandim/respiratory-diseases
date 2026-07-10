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
