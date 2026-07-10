# 🩺 Classificador de Síndrome Respiratória Aguda Grave (SRAG/COVID-19)

Frontend em Streamlit que consulta um modelo **XGBoost multiclasse**, treinado sobre dados públicos do DATASUS, para sugerir a classificação final de um caso notificado de Síndrome Respiratória Aguda Grave — com pipeline de treino, empacotamento e serviço de inferência hospedados na AWS a custo efetivamente zero quando ocioso.

![Python](https://img.shields.io/badge/python-3.11-blue?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/streamlit-1.38%2B-FF4B4B?logo=streamlit&logoColor=white)
![XGBoost](https://img.shields.io/badge/xgboost-3.2-0066CC)
![AWS Lambda](https://img.shields.io/badge/AWS-Lambda-FF9900?logo=awslambda&logoColor=white)
![License](https://img.shields.io/github/license/guigrandim/respiratory-diseases)

**Demo ao vivo:** https://jlqsegnebs6r6sy7sn3ebxskxy0ihkkx.lambda-url.us-east-1.on.aws/
*(o serviço hiberna quando ocioso; a primeira visita pode levar ~1-2 minutos para acordar o ECS — veja a seção "Deploy")*

<p align="center">
<img src="./assets/img/arquitetura.png" alt="Diagrama de arquitetura: SIVEP-Gripe/DATASUS → S3 → Glue Catalog → S3 (train.parquet) → Notebook (feature engineering + treino XGBoost) → model.pkl (S3); Formulário Streamlit → ECS Fargate → AWS Lambda → model.pkl" width="800px">
</p>

### 🎯 Destaques
- Construí, do zero, um classificador multiclasse (5 classes de `classi_fin`) com pipeline completo — treino, empacotamento, inferência e frontend — em produção na AWS, contornando a falta de cota de SageMaker Endpoint na conta.
- Modelo com **68% de acurácia** e **F1 ponderado de 0.67** no conjunto de teste (nunca visto durante treino/early stopping).
- Reduzi o custo de infraestrutura a efetivamente zero quando ocioso: o serviço ECS liga sozinho sob demanda (Lambda "porteira") e desliga automaticamente após um limite de tempo, sem load balancer nem servidor sempre ligado.
- Investiguei e documentei a procedência de uma feature crítica não documentada oficialmente pelo DATASUS, em vez de ignorar a lacuna.

---

## 🚨 Problema de Negócio

O DATASUS disponibiliza publicamente os dados do SIVEP-Gripe (Sistema de Informação da Vigilância Epidemiológica da Gripe) — notificações de Síndrome Respiratória Aguda Grave, com dados clínicos e de atendimento de cada caso. Hoje, sugerir a classificação final de um caso notificado (`classi_fin`: Influenza, outro vírus respiratório, outro agente etiológico, não especificado ou COVID-19) depende inteiramente da avaliação manual de quem preenche a ficha, sem nenhuma triagem automatizada assistida por dados históricos.

O caminho "padrão" para servir um modelo de ML na AWS seria treinar e publicar via SageMaker Estimator/Endpoint gerenciado — mas a conta AWS usada neste projeto não tinha cota liberada para instâncias `ml.*`, e o SageMaker Local Mode com o container built-in do XGBoost apresentou um bug de compatibilidade (`KeyError: 'S3DistributionType'`) que impedia o treino de completar.

**Pergunta central:** é possível construir e servir, de ponta a ponta, um classificador multiclasse confiável para SRAG usando apenas dados públicos do DATASUS — sem depender de nenhum recurso gerenciado de ML da AWS, e gastando o mínimo possível de infraestrutura, já que é um projeto de portfólio sem tráfego constante?

**Minha tarefa:** projetar e implementar sozinho todo o pipeline — engenharia de features, treino nativo do XGBoost, empacotamento e serviço de inferência via Lambda, frontend Streamlit e a infraestrutura de deploy na AWS com custo ocioso zero.

---

## 🗺️ Planejamento da Solução

1. **Ingestão e validação** — materializar o histórico do SIVEP-Gripe (já catalogado no Glue) em `train.parquet` via Athena, validando schema e contagem de linhas contra o catálogo antes de prosseguir.
2. **Descrição e limpeza dos dados** — renomear colunas, checar dimensões, tratar valores ausentes, estatística descritiva.
3. **Análise estatística e EDA** — amostragem, análise univariada da variável-alvo, distribuição das variáveis numéricas, correlações.
4. **Validação de hipóteses (H1-H7)** — confrontar suposições de negócio sobre o perfil dos casos com o que os dados de fato mostram (ver "Top Insights" abaixo).
5. **Engenharia de features** — faixa etária, score de comorbidades, macro-região, sazonalidade via seno/cosseno da semana epidemiológica, score vacinal.
6. **Treino nativo do XGBoost** — sem depender do Estimator/Local Mode do SageMaker (bloqueado por bug de compatibilidade e falta de cota), com early stopping e split estratificado treino/validação/teste.
7. **Empacotamento e inferência via Lambda** — modelo serializado em `pickle`, servido por uma AWS Lambda em container (Docker + ECR), sem nenhum SageMaker Endpoint envolvido.
8. **Frontend e deploy** — Streamlit containerizado em ECS Fargate, com infraestrutura de start/stop automática para custo ocioso zero.

**Ferramentas:** Python, XGBoost, pandas, AWS (Athena, Glue, S3, Lambda, ECR, ECS Fargate, EventBridge), Docker, Streamlit, pytest.

---

## 🛠️ Desenvolvimento

### Dataset

| | |
|---|---|
| **Fonte** | SIVEP-Gripe (DATASUS), via `database_health_bridge.table_train_gg_solutionstrain` (Glue Catalog / Athena) |
| **Unidade** | um caso notificado de Síndrome Respiratória Aguda Grave |
| **Variável-alvo** | `classi_fin` — 5 classes válidas segundo o dicionário oficial (Influenza, outro vírus respiratório, outro agente etiológico, não especificado, COVID-19); códigos residuais (6) e "ignorado" (9) são filtrados antes do split, por não serem categorias clínicas reais |
| **Split** | 70% treino / 15% validação / 15% teste, estratificado por `classi_fin` — o conjunto de teste nunca influencia o treino nem o critério de parada do early stopping |

### Features do modelo

11 features entram no XGBoost, todas calculadas em `common.py`/no notebook a partir dos campos brutos do SIVEP-Gripe: `raiox_res`, `fnt_in_cov`, `delta_uti`, `amostra`, `hospital`, `faixa_etaria_cod` (criança/jovem/adulto/idoso, a partir da idade), `score_comorbidades` (soma de 11 condições crônicas), `macro_regiao_cod` (a partir da UF), `sem_pri_sin`/`sem_pri_cos` (sazonalidade da semana epidemiológica dos primeiros sintomas), `score_vacinal` (soma de 5 campos de vacinação).

O modelo é treinado com `objective='multi:softmax'` e, em produção, o `objective` é ajustado para `multi:softprob` **sem retreino** — mesmo booster, mesma árvore, só a função de saída muda — para expor a probabilidade de cada uma das 5 classes por caso, não só o rótulo vencedor.

### Estrutura do Projeto

```
.
├── home.py                          # página inicial: visão geral e dicionário de campos
├── pages/
│   └── 1_Formulario.py              # formulário de entrada e exibição da previsão
├── common.py                        # constantes e lógica compartilhada (labels, features, invocação da Lambda)
├── notebooks/
│   └── training_pipeline.ipynb      # notebook de treino (fonte da verdade)
├── scripts/
│   ├── lambda_wake/                 # Lambda "porteira": liga o ECS sob demanda, é o link fixo do projeto
│   └── parar_app.sh                 # desliga o serviço ECS manualmente
├── tests/                           # testes unitários (pytest) da lambda_wake
├── assets/
│   ├── 14075330-ficha-srag-hospitalizado-...pdf  # ficha oficial de notificação do SIVEP-Gripe
│   └── img/arquitetura.png          # diagrama de arquitetura
├── Dockerfile
└── requirements.txt
```

### Como Executar Localmente

Requer credenciais AWS configuradas (`~/.aws/credentials`) com permissão de `lambda:InvokeFunction` na função configurada em `LAMBDA_FUNCTION_NAME` (variável de ambiente, default `requisicoes_ml_sagemaker`).

```bash
git clone https://github.com/guigrandim/respiratory-diseases.git
cd respiratory-diseases
pip install -r requirements.txt
streamlit run home.py
```

Ou via Docker:

```bash
docker build -t respiratory-diseases-app .
docker run -p 8501:8501 -v ~/.aws:/root/.aws:ro respiratory-diseases-app
```

### Deploy (ECS Fargate) — liga sozinho sob demanda

O app roda em um serviço ECS Fargate (`respiratory-diseases-cluster` / `respiratory-diseases-task-service-l0kgkxxb`), mas **fica parado por padrão** (`desiredCount=0`) para não gerar custo contínuo.

- **Ligar**: automático. Uma Lambda pública ("porteira", `respiratory-diseases-wake`, código em `scripts/lambda_wake/`) é o link fixo do projeto. Ao receber uma requisição, ela confere o estado do serviço ECS; se estiver parado, chama `ecs:UpdateService` para subir e devolve uma página HTML que se auto-atualiza a cada ~10s; quando a task está `RUNNING` e passou de uma janela de warm-up, devolve um redirect 302 direto para o IP público da task (`http://<ip>:8501`) — dali em diante o navegador fala direto com o Fargate, sem a Lambda no meio, então o WebSocket do Streamlit funciona normalmente.
- **Desligar na hora**: `scripts/parar_app.sh`.
- **Auto-stop**: uma função Lambda (`respiratory-diseases-auto-stop`), disparada a cada 10 minutos por uma regra do EventBridge, derruba o serviço automaticamente depois de 2h de uptime (`MAX_UPTIME_MINUTES`, env var da Lambda) — não é detecção de tráfego, é um limite de tempo de sessão.
- Nenhum ALB/NLB é usado (custo fixo extra não valeria a pena para o volume de tráfego deste projeto) — a porteira usa só a Function URL nativa da Lambda.

---

## 💡 Top Insights

Validação de 7 hipóteses de negócio (H1-H7) sobre o perfil dos casos, confrontadas diretamente com os dados do SIVEP-Gripe.

### 1. 🤔 Zona urbana tem MENOS proporção de COVID que a zona rural — o oposto do esperado
A hipótese era que a zona urbana concentraria mais casos de COVID por maior densidade populacional. Nos dados, é o contrário: 28,6% dos casos em zona urbana são COVID, contra 31,8% na zona rural — sem evidência de maior tendência urbana.

### 2. 📅 O pico de casos não acompanha as semanas mais frias do ano
A expectativa era de sazonalidade tipo gripe (mais casos no inverno). O pico real ocorre nas semanas epidemiológicas 1-20 (verão/outono no Brasil), caindo até a semana ~40 e subindo de novo no fim do ano — um padrão que parece refletir mais as ondas de COVID-19 do que sazonalidade climática.

### 3. 💉 Não vacinados são maioria entre os casos de COVID, mas a margem é pequena
Entre os casos de COVID, 43,1% não tomaram a vacina contra COVID-19, contra 38,1% que tomaram (18,8% ignorado) — a hipótese é só parcialmente confirmada: o grupo não vacinado é o maior, mas por uma margem pequena, não avassaladora.

### 4. 🐣 "Sempre" ter sintoma respiratório por contato com aves/suínos não se confirma
77,8% de quem trabalha com aves/suínos teve dispneia — não 100%/"sempre" como a hipótese propunha — e a diferença para quem não tem esse contato (73,7%) é pequena, insuficiente para sustentar uma relação causal forte.

### 5. 👶 Pacientes de "outro vírus respiratório" são muito mais jovens que as demais classes
Ainda que a hipótese de idade x tendência não seja mensurável nesta base (não há grupo de controle sem a doença), o boxplot revela um padrão útil para o modelo: a classe 2 (outro vírus respiratório) concentra pacientes com mediana de idade ~8 anos, enquanto as demais classes ficam entre 50-70 anos — provavelmente por isso `faixa_etaria_cod` tem peso relevante na classificação.

> Duas hipóteses (fumantes, interior x capital de SC) não puderam ser validadas por limitação de dado — sem coluna de tabagismo no SIVEP-Gripe, e sem de-para IBGE de município para capital/interior. Documentado como limitação em vez de forçar uma resposta sem lastro.

---

## 📊 Resultados

### Resultado do Modelo

68% de acurácia e F1 ponderado de 0,67 no conjunto de teste — nunca visto durante o treino nem usado no critério de parada do early stopping (o split anterior de 80/20 reaproveitava o próprio teste como validação, o que enviesava a métrica; o split atual usa 70/15/15 estratificado justamente para eliminar esse viés).

### Resultado da Entrega

- Pipeline ponta a ponta em produção na AWS (Streamlit → Lambda → XGBoost), sem nenhum SageMaker Endpoint — contornando por completo a falta de cota `ml.*` da conta.
- Custo de infraestrutura efetivamente zero quando ocioso: o ECS Fargate fica com `desiredCount=0` por padrão e liga sozinho, sob demanda, na primeira visita real ao link — sem ALB/NLB, sem servidor sempre ligado.
- Link público permanente e estável (a Lambda "porteira" resolve o IP dinâmico do Fargate a cada visita), eliminando o processo manual de religar o serviço e reescrever o link a cada demonstração.
- Código revisado por um agente independente antes de ir para produção, corrigindo dependências não usadas e uma imagem-base desatualizada no Dockerfile.

---

## ✅ Conclusões

O projeto resolve, de ponta a ponta, o problema de classificar automaticamente notificações de SRAG a partir de dados públicos do DATASUS — sem depender de nenhum recurso gerenciado de ML da AWS (indisponível na conta usada) — e entrega isso como um produto real, hospedado, com custo de infraestrutura ocioso próximo de zero, o que era um requisito tão importante quanto a acurácia do modelo em si para um projeto de portfólio.

**Próximos passos:**
- Confirmar com a equipe de origem do dado a definição exata de `delta_uti` (feature de maior peso no modelo, mas não documentada oficialmente).
- Enriquecer a base com fontes externas (ex: de-para IBGE capital/interior, dado de tabagismo) para validar as hipóteses hoje sem lastro suficiente.
- Avaliar métricas por classe (não só agregadas) dado o desbalanceamento observado entre categorias de `classi_fin`.

**Limitações:**
- `delta_uti`, a feature de maior peso no modelo treinado (maior `gain`/`total_gain`/`cover` das 11 features), não existe no dicionário oficial de dados do SIVEP-Gripe (conferido no PDF oficial de 19/09/2022, opendatasus.saude.gov.br). A leitura de trabalho é que se trata de um valor calculado a partir dos campos oficiais **54 - Data de entrada na UTI** (`DT_ENTUTI`) e **55 - Data de saída na UTI** (`DT_SAIDUTI`) — consistente com a distribuição observada dos valores, mas não é uma definição publicada pelo DATASUS com esse nome. Antes de usar este modelo em um contexto clínico real, vale confirmar a definição exata com quem construiu o pipeline de dados de origem.
- Duas hipóteses de negócio (tabagismo, interior x capital de SC) não puderam ser validadas por limitação do dado disponível.
- O dataset contém apenas casos já notificados de SRAG (sem grupo de controle sem a doença), então relações de "tendência" com variáveis como idade não são estatisticamente mensuráveis nesta base.

---

*Fonte de dados: SIVEP-Gripe/DATASUS · Metodologia: CRISP-DS · Stack: Python, XGBoost, AWS (Lambda, ECS Fargate, Athena, Glue), Streamlit*

## 🧰 Skills Demonstradas

- **Técnicas**: engenharia de features (sazonalidade cíclica, scores agregados), validação de hipóteses estatísticas, split estratificado sem vazamento de dado, empacotamento e serving de modelo fora de plataformas gerenciadas de ML, infraestrutura serverless de custo sob demanda (Lambda + ECS Fargate), testes unitários (pytest) para lógica de infraestrutura.
- **De negócio**: tradução de restrição de conta AWS (falta de cota `ml.*`) em decisão de arquitetura, investigação de procedência de dado não documentado em vez de descartá-lo, priorização de custo operacional para um projeto sem tráfego constante.

## 👩‍💻 Autor

Desenvolvido por Guilherme Grandim como um projeto de portfólio em ciência de dados / ML.
LinkedIn: [linkedin.com/in/guilherme-grandim](https://www.linkedin.com/in/guilherme-grandim)
E-mail: [gui.grandim@gmail.com](mailto:gui.grandim@gmail.com)

## 📄 Licença

Este projeto está sob a licença MIT — veja [LICENSE](./LICENSE) para detalhes.
