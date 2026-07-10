# Design: Lambda "porteira" (wake-on-request) para o serviço ECS

Data: 2026-07-10

## Contexto

O app Streamlit roda em um serviço ECS Fargate (`respiratory-diseases-cluster` /
`respiratory-diseases-task-service-l0kgkxxb`) sem load balancer. Hoje ele fica
parado por padrão (`desiredCount=0`) e é ligado manualmente via
`scripts/iniciar_app.sh` (que também reescreve o link no README, já que o IP
público muda a cada start) e desligado via `scripts/parar_app.sh` ou
automaticamente após 2h de uptime por uma Lambda de auto-stop
(`respiratory-diseases-auto-stop`, disparada a cada 10min via EventBridge).

Objetivo desta mudança: eliminar o passo manual de "ligar" — o serviço deve
acordar sozinho quando alguém acessa o link, e ficar hibernado
(`desiredCount=0`, custo zero) o resto do tempo. Sem adicionar custo fixo de
infraestrutura (ALB, NLB, VPC Link) — inviável para o volume de tráfego de um
projeto de portfólio.

## Alternativas consideradas

- **Migrar para Lambda Web Adapter** (Streamlit rodando dentro de uma Lambda
  via Function URL): descartado — Function URLs não suportam WebSocket, só
  request/response ou streaming HTTP unidirecional, e o Streamlit depende de
  uma conexão persistente (WS, com fallback de polling degradado) para
  reatividade. O modelo de execução stateless/efêmero do Lambda também é mal
  adequado ao estado de sessão em memória do Streamlit.
- **AWS App Runner**: descartado — não tem scale-to-zero automático por
  ociosidade (só pause manual) e parou de aceitar clientes novos a partir de
  31/03/2026.
- **ECS + ALB com scale-on-request**: tecnicamente mais "canônico" (escala
  com base em `RequestCount` real via CloudWatch), mas o ALB tem custo fixo
  rodando 24/7 (~US$16-20/mês) independente de tráfego — mais caro que o
  Fargate ocioso que já é zero hoje. Descartado para este projeto.
- **Manter como está, só ajustar o timer de auto-stop**: não resolve o
  pedido (ainda depende de start manual).

## Solução escolhida: Lambda porteira (wake-and-redirect)

Uma nova Lambda pública (via Function URL, sem custo de domínio/ALB) vira o
link estável do projeto, substituindo o IP dinâmico reescrito no README a
cada start.

### Fluxo de requisição

1. Visitante acessa a Function URL fixa.
2. A Lambda consulta `ecs:DescribeServices` / `ecs:ListTasks` no cluster e
   serviço já existentes.
3. Se não há task rodando (`desiredCount=0` ou nenhuma task `RUNNING`):
   chama `ecs:UpdateService --desired-count 1` (idempotente — chamadas
   repetidas não causam efeito colateral) e devolve uma página HTML de
   espera ("iniciando, aguarde...") que se auto-atualiza a cada ~10s via
   `<meta http-equiv="refresh">`, reinvocando a própria Lambda.
4. Se há task `RUNNING` mas iniciada há menos de ~20s (janela de warm-up —
   sem load balancer não há health check disponível; usa-se o tempo desde
   `task.startedAt` como proxy de "o processo Streamlit já deve estar de
   pé"), continua devolvendo a página de espera.
5. Quando a task está `RUNNING` e passou da janela de warm-up: busca o IP
   público atual via ENI (mesma lógica hoje em `iniciar_app.sh` —
   `describe-tasks` → `networkInterfaceId` → `describe-network-interfaces`)
   e devolve um redirect HTTP 302 para `http://<ip>:8501`. Dali em diante o
   navegador fala diretamente com o Fargate, então o WebSocket do Streamlit
   funciona normalmente, sem a Lambda no meio.
6. Se a task nunca ficar saudável (falha real), a página de espera
   simplesmente continua tentando indefinidamente — sem timeout explícito
   nem mensagem de erro dedicada (decisão consciente: manter simples; esse
   caso é raro porque a imagem/task não muda).

O auto-stop por ociosidade (`respiratory-diseases-auto-stop` + EventBridge)
não muda — continua desligando o serviço depois do tempo limite configurado.
Esta mudança afeta apenas *como o serviço liga*, não como desliga.

### Implementação

- Novo arquivo `scripts/lambda_wake/handler.py` — Python puro, só `boto3`
  (já embutido no runtime Lambda, sem necessidade de imagem Docker).
- Variáveis de ambiente: `CLUSTER`, `SERVICE`, `REGION`, `PORT` (mesmos
  valores hoje hardcoded nos scripts shell).
- Function URL com `AUTH_TYPE=NONE` (pública — é o objetivo) e
  `reserved-concurrency=1` como trava barata contra corridas de chamadas
  paralelas.
- Nova role de execução (`respiratory-diseases-wake-role`) com permissão
  mínima: `ecs:DescribeServices`, `ecs:UpdateService`, `ecs:ListTasks`,
  `ecs:DescribeTasks`, `ec2:DescribeNetworkInterfaces` restritas ao
  cluster/serviço existentes, mais permissão básica de logging no
  CloudWatch Logs.

### Mudanças em scripts existentes

- Remove `scripts/iniciar_app.sh` — a Lambda substitui o start manual.
- `scripts/parar_app.sh` continua existindo (desligar na hora, sem esperar
  auto-stop), mas **remove a lógica que reescrevia o "Link atual" do README
  como offline** — o link agora é permanente e sempre funcional (ele mesmo
  acorda o serviço na próxima visita), então marcar como "offline" seria
  enganoso.

### Mudanças no README

- Seção "Demo ao vivo": troca o link dinâmico + texto "me contate" pelo link
  fixo da Function URL, com nota explicando que o primeiro acesso após
  período ocioso leva ~1-2min para o ECS acordar.
- Seção "Deploy": documenta a Lambda porteira (comandos `aws lambda
  create-function` / `create-function-url-config`, a role IAM) no lugar do
  passo de `iniciar_app.sh`; a explicação do auto-stop permanece como está.

## Custo

Essencialmente zero de infraestrutura adicional — Lambda porteira dentro do
free tier (invocações raras), sem ALB/NLB/VPC Link. Custo do ECS Fargate
continua sendo cobrado apenas enquanto uma task está de fato rodando, como
hoje.

## Fora de escopo

- Autenticação/proteção contra abuso do link público (qualquer pessoa pode
  acordar o ECS e gerar custo de Fargate durante o tempo de uptime). Aceito
  como trade-off de um projeto de portfólio público; o auto-stop por tempo
  limita o dano.
- Mudar a lógica do auto-stop (continua baseada em tempo, não em tráfego
  real).
- Domínio próprio / CloudFront — usa a Function URL padrão da AWS.
