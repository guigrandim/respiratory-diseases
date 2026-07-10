import math

import pandas as pd
import streamlit as st

from common import (
    CLASSI_FIN_LABELS,
    COMORBIDADE_FIELDS,
    FNT_IN_COV_OPTIONS,
    INVERSE_LABEL_MAPPING,
    LAMBDA_FUNCTION_NAME,
    MODEL_COLUMNS,
    RAIOX_RES_OPTIONS,
    REGIAO_TO_COD,
    SIM_NAO_IGNORADO,
    UF_TO_REGIAO,
    VACINA_FIELDS,
    calcular_faixa_etaria_cod,
    invocar_lambda,
)

st.set_page_config(page_title="Formulário Médico", page_icon="📋")

st.title("Formulário de previsão")
st.caption(
    "Precisa de ajuda para entender os códigos usados nos campos abaixo? "
    "Veja a página inicial."
)

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
                "Não consta com esse nome no dicionário oficial do SIVEP-Gripe. "
                "É a feature mais influente do modelo treinado (maior gain/"
                "total_gain/cover de todas). Leitura de trabalho da equipe: "
                "calculado a partir dos campos oficiais 54-Data de entrada na "
                "UTI (DT_ENTUTI) e 55-Data de saída da UTI (DT_SAIDUTI) — não "
                "é uma definição publicada pelo DATASUS, é uma interpretação "
                "baseada em evidências indiretas. Veja a página inicial para "
                "mais detalhes."
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
        probabilidades = invocar_lambda(instancia)
        predicao_0idx = max(range(len(probabilidades)), key=probabilidades.__getitem__)
        classi_fin = INVERSE_LABEL_MAPPING[predicao_0idx]
        rotulo = CLASSI_FIN_LABELS[classi_fin]

        st.success(f"Classificação prevista: **{rotulo}**")

        probs_por_classe = {
            CLASSI_FIN_LABELS[INVERSE_LABEL_MAPPING[idx]]: prob
            for idx, prob in enumerate(probabilidades)
        }
        serie_probs = pd.Series(probs_por_classe).sort_values(ascending=False)
        st.bar_chart(serie_probs)

        with st.expander("Detalhes técnicos"):
            st.write("Features enviadas ao modelo (ordem exata):", dict(zip(MODEL_COLUMNS, instancia)))
            st.write("Classe 0-indexada retornada pelo Lambda:", predicao_0idx)
            st.write("Vetor de probabilidades bruto:", probabilidades)
    except Exception as exc:
        st.error(f"Erro ao chamar a função Lambda '{LAMBDA_FUNCTION_NAME}': {exc}")
