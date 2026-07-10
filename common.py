import json
import os

import boto3
import pandas as pd
import streamlit as st

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
LAMBDA_FUNCTION_NAME = os.environ.get("LAMBDA_FUNCTION_NAME", "requisicoes_ml_sagemaker")

# label_mapping do notebook (secao 5.1): classi_fin original -> label do modelo (0-based)
LABEL_MAPPING = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4}
INVERSE_LABEL_MAPPING = {modelo: original for original, modelo in LABEL_MAPPING.items()}

CLASSI_FIN_LABELS = {
    1: "Influenza",
    2: "Outro vírus respiratório",
    3: "Outro agente etiológico",
    4: "Não especificado",
    5: "COVID-19",
}

# Ordem EXATA das colunas do modelo (notebook, secao 3.0/4.5)
MODEL_COLUMNS = [
    "raiox_res", "fnt_in_cov", "delta_uti", "amostra", "hospital",
    "faixa_etaria_cod", "score_comorbidades", "macro_regiao_cod",
    "sem_pri_sin", "sem_pri_cos", "score_vacinal",
]

UF_TO_REGIAO = {
    "AC": "Norte", "AP": "Norte", "AM": "Norte", "PA": "Norte", "RO": "Norte", "RR": "Norte", "TO": "Norte",
    "AL": "Nordeste", "BA": "Nordeste", "CE": "Nordeste", "MA": "Nordeste", "PB": "Nordeste",
    "PE": "Nordeste", "PI": "Nordeste", "RN": "Nordeste", "SE": "Nordeste",
    "DF": "Centro-Oeste", "GO": "Centro-Oeste", "MT": "Centro-Oeste", "MS": "Centro-Oeste",
    "ES": "Sudeste", "MG": "Sudeste", "RJ": "Sudeste", "SP": "Sudeste",
    "PR": "Sul", "RS": "Sul", "SC": "Sul",
}

# Ordem travada manualmente (alfabetica das 5 regioes) para reproduzir o
# .astype('category').cat.codes do notebook sem depender da ordenacao
# implicita/instavel do pandas.
REGIAO_TO_COD = {
    "Centro-Oeste": 0,
    "Nordeste": 1,
    "Norte": 2,
    "Sudeste": 3,
    "Sul": 4,
}

RAIOX_RES_OPTIONS = {
    1: "1 - Normal",
    2: "2 - Infiltrado intersticial",
    3: "3 - Consolidação",
    4: "4 - Misto",
    5: "5 - Outro",
    6: "6 - Não realizado",
    9: "9 - Ignorado",
}

SIM_NAO_IGNORADO = {1: "1 - Sim", 2: "2 - Não", 9: "9 - Ignorado"}

FNT_IN_COV_OPTIONS = {1: "1 - Manual", 2: "2 - Integração (Base Nacional de Vacinação)"}

# Colunas de comorbidade somadas em score_comorbidades (notebook, secao 3.0)
COMORBIDADE_FIELDS = [
    ("cardiopati", "Doença Cardiovascular Crônica"),
    ("hematologi", "Doença Hematológica Crônica"),
    ("sind_down", "Síndrome de Down"),
    ("hepatica", "Doença Hepática Crônica"),
    ("asma", "Asma"),
    ("diabetes", "Diabetes mellitus"),
    ("neurologic", "Doença Neurológica Crônica"),
    ("pneumopati", "Outra Pneumopatia Crônica"),
    ("imunodepre", "Imunodeficiência/Imunodepressão"),
    ("renal", "Doença Renal Crônica"),
    ("obesidade", "Obesidade"),
]

# Colunas de vacinacao somadas em score_vacinal (notebook, secao 3.0)
VACINA_FIELDS = [
    ("vacina", "Recebeu vacina contra Gripe na última campanha?"),
    ("vacina_cov", "Recebeu vacina COVID-19?"),
    ("dose_1_cov", "Tomou 1ª dose da vacina COVID-19?"),
    ("dose_2_cov", "Tomou 2ª dose da vacina COVID-19?"),
    ("dose_ref", "Tomou dose de reforço da vacina COVID-19?"),
]


@st.cache_resource
def get_lambda_client():
    return boto3.client("lambda", region_name=AWS_REGION)


def calcular_faixa_etaria_cod(idade, idade_ignorada):
    if idade_ignorada:
        return -1
    faixa = pd.cut(
        [idade],
        bins=[-1, 12, 18, 60, 200],
        labels=["crianca", "jovem", "adulto", "idoso"],
    )
    codigo = faixa.codes[0]
    return int(codigo)


def invocar_lambda(instancia):
    client = get_lambda_client()
    response = client.invoke(
        FunctionName=LAMBDA_FUNCTION_NAME,
        InvocationType="RequestResponse",
        Payload=json.dumps({"instances": [instancia]}),
    )
    if response.get("FunctionError"):
        raise RuntimeError(response["Payload"].read().decode("utf-8"))
    payload = json.loads(response["Payload"].read())
    body = json.loads(payload["body"])
    return body["predictions"][0]
