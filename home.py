import streamlit as st

from common import CLASSI_FIN_LABELS, FNT_IN_COV_OPTIONS, RAIOX_RES_OPTIONS, SIM_NAO_IGNORADO

st.set_page_config(page_title="SRAG/COVID - Sobre o projeto", page_icon="📋")

st.title("Classificação de Síndrome Respiratória Aguda Grave (SRAG)")

# Texto introdutorio: explica o modelo (XGBoost), a fonte dos dados
# (SIVEP-Gripe) e a arquitetura (Streamlit -> Lambda -> SageMaker).
st.markdown(
    """
Esta ferramenta usa um modelo **XGBoost multiclasse**, treinado sobre dados do
**SIVEP-Gripe** (Sistema de Informação da Vigilância Epidemiológica da Gripe,
DATASUS), para sugerir a classificação final (`classi_fin`) de um caso de
Síndrome Respiratória Aguda Grave a partir de dados clínicos e de atendimento.

**Arquitetura:** o formulário abaixo envia os dados para uma função **AWS
Lambda** (via boto3), que carrega o modelo treinado no SageMaker e devolve a
classe prevista com a probabilidade de cada uma das 5 classes possíveis.
"""
)

# Tabela de referencia: mostra o significado de cada codigo 1-5 de
# classi_fin, a variavel que o modelo prevê.
st.subheader("Classes de saída (classi_fin)")
st.table(
    {
        "Código": list(CLASSI_FIN_LABELS.keys()),
        "Classificação": list(CLASSI_FIN_LABELS.values()),
    }
)

# Dicionario de dados: explica os codigos usados nos campos do formulario
# que nao sao autoexplicativos (a maioria vem direto do dicionario oficial
# do SIVEP-Gripe).
st.subheader("Dicionário de campos do formulário")
st.markdown(
    "As comorbidades e a situação vacinal são preenchidas como perguntas "
    "diretas (sim/não) e não precisam de explicação adicional. Os campos "
    "abaixo usam códigos do SIVEP-Gripe e estão detalhados aqui:"
)

st.markdown("**Houve internação? (`hospital`) / Coletou amostra? (`amostra`)**")
st.table({"Código": list(SIM_NAO_IGNORADO.keys()), "Significado": list(SIM_NAO_IGNORADO.values())})

st.markdown("**Resultado do Raio X de Tórax (`raiox_res`)**")
st.table({"Código": list(RAIOX_RES_OPTIONS.keys()), "Significado": list(RAIOX_RES_OPTIONS.values())})

st.markdown("**Fonte dos dados de vacinação COVID-19 (`fnt_in_cov`)**")
st.table({"Código": list(FNT_IN_COV_OPTIONS.keys()), "Significado": list(FNT_IN_COV_OPTIONS.values())})

# Campos calculados (nao sao input direto do usuario, sao derivados no
# formulario) e a explicacao/ressalva sobre delta_uti, que e a feature de
# maior peso no modelo mas nao consta no dicionario oficial do SIVEP-Gripe.
st.markdown(
    """
**Faixa etária (`faixa_etaria_cod`)**: calculada a partir da idade —
criança (0-12 anos), jovem (13-18), adulto (19-60), idoso (61+).

**Região (`macro_regiao_cod`)**: calculada a partir da UF informada —
Centro-Oeste=0, Nordeste=1, Norte=2, Sudeste=3, Sul=4.

**Semana epidemiológica de 1ºs sintomas (`sem_pri`)**: usada para calcular o
componente sazonal do modelo (`sem_pri_sin`/`sem_pri_cos`).

**`delta_uti`** ⚠️: é a feature de **maior peso** no modelo treinado (maior
`gain`/`total_gain`/`cover` das 11 features), mas o nome não existe no
dicionário oficial do SIVEP-Gripe. A leitura de trabalho da equipe é que se
trata de um valor calculado a partir dos campos oficiais **54 - Data de
entrada na UTI** (`DT_ENTUTI`) e **55 - Data de saída da UTI** (`DT_SAIDUTI`)
— não é uma definição publicada pelo DATASUS com esse nome, é uma
interpretação baseada em evidências indiretas (distribuição dos valores e
ausência de colunas de data brutas na tabela de origem).
"""
)

# Link de navegacao para a pagina do formulario de previsao propriamente dito.
st.page_link("pages/1_Formulario.py", label="Ir para o formulário de previsão", icon="➡️")
