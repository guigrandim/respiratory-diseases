import json
import math
import os

import boto3
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Formulário Médico", page_icon="📋")

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


st.title("Classificação de Síndrome Respiratória Aguda Grave (SRAG)")

with st.form(key="form_srag"):
    st.subheader("Dados clínicos e de atendimento")
    col1, col2 = st.columns(2)
    with col1:
        hospital = st.selectbox(
            "Houve internação? (hospital)",
            options=list(SIM_NAO_IGNORADO.keys()),
            format_func=lambda c: SIM_NAO_IGNORADO[c],
        )
        amostra = st.selectbox(
            "Coletou amostra? (amostra)",
            options=list(SIM_NAO_IGNORADO.keys()),
            format_func=lambda c: SIM_NAO_IGNORADO[c],
        )
        raiox_res = st.selectbox(
            "Resultado do Raio X de Tórax (raiox_res)",
            options=list(RAIOX_RES_OPTIONS.keys()),
            format_func=lambda c: RAIOX_RES_OPTIONS[c],
        )
    with col2:
        fnt_in_cov = st.selectbox(
            "Fonte dos dados de vacinação COVID-19 (fnt_in_cov)",
            options=list(FNT_IN_COV_OPTIONS.keys()),
            format_func=lambda c: FNT_IN_COV_OPTIONS[c],
        )
        delta_uti = st.number_input(
            "delta_uti",
            value=0,
            step=1,
            help=(
                "Coluna não documentada no dicionário oficial do SIVEP-Gripe "
                "(assim como 'id') — sem definição confirmada."
            ),
        )

    st.subheader("Dados do paciente")
    col3, col4 = st.columns(2)
    with col3:
        idade_ignorada = st.checkbox("Idade ignorada/não informada")
        idade = st.number_input(
            "Idade (anos)", min_value=0, max_value=150, value=30, disabled=idade_ignorada
        )
    with col4:
        sg_uf = st.selectbox("UF (sg_uf)", sorted(UF_TO_REGIAO.keys()))
        sem_pri = st.number_input(
            "Semana epidemiológica de 1ºs sintomas (sem_pri)", min_value=1, max_value=53, value=1
        )

    st.subheader("Comorbidades")
    comorbidade_cols = st.columns(3)
    comorbidades = {}
    for i, (campo, rotulo) in enumerate(COMORBIDADE_FIELDS):
        with comorbidade_cols[i % 3]:
            comorbidades[campo] = st.checkbox(rotulo, key=f"com_{campo}")

    st.subheader("Vacinação")
    vacina_cols = st.columns(2)
    vacinas = {}
    for i, (campo, rotulo) in enumerate(VACINA_FIELDS):
        with vacina_cols[i % 2]:
            vacinas[campo] = st.checkbox(rotulo, key=f"vac_{campo}")

    submitted = st.form_submit_button("Prever classificação")

if submitted:
    faixa_etaria_cod = calcular_faixa_etaria_cod(idade, idade_ignorada)
    score_comorbidades = sum(1 for v in comorbidades.values() if v)
    macro_regiao_cod = REGIAO_TO_COD[UF_TO_REGIAO[sg_uf]]
    sem_pri_sin = math.sin(2 * math.pi * sem_pri / 52)
    sem_pri_cos = math.cos(2 * math.pi * sem_pri / 52)
    score_vacinal = sum(1 for v in vacinas.values() if v)

    valores = {
        "raiox_res": raiox_res,
        "fnt_in_cov": fnt_in_cov,
        "delta_uti": delta_uti,
        "amostra": amostra,
        "hospital": hospital,
        "faixa_etaria_cod": faixa_etaria_cod,
        "score_comorbidades": score_comorbidades,
        "macro_regiao_cod": macro_regiao_cod,
        "sem_pri_sin": sem_pri_sin,
        "sem_pri_cos": sem_pri_cos,
        "score_vacinal": score_vacinal,
    }
    # fillna(0) do notebook (secao 3.0) para valores ausentes
    instancia = [valores[col] if valores[col] is not None else 0 for col in MODEL_COLUMNS]

    try:
        predicao_0idx = int(round(invocar_lambda(instancia)))
        classi_fin = INVERSE_LABEL_MAPPING[predicao_0idx]
        rotulo = CLASSI_FIN_LABELS[classi_fin]

        st.success(f"Classificação prevista: **{rotulo}**")
        st.caption(
            "O Lambda atual usa objective='multi:softmax' e retorna apenas a classe "
            "prevista (sem probabilidade por classe) — não há confiança/probabilidade "
            "para exibir com a implementação atual do lambda_function.py."
        )
        with st.expander("Detalhes técnicos"):
            st.write("Features enviadas ao modelo (ordem exata):", dict(zip(MODEL_COLUMNS, instancia)))
            st.write("Classe 0-indexada retornada pelo Lambda:", predicao_0idx)
    except Exception as exc:
        st.error(f"Erro ao chamar a função Lambda '{LAMBDA_FUNCTION_NAME}': {exc}")
