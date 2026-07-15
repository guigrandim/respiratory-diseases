"""Builds the two possible HTTP responses the wake-on-request lambda returns."""

# Página de espera: usa refresh automático via meta tag (a cada 10s) em vez
# de JS, para funcionar mesmo se o visitante tiver JavaScript desabilitado.
WAIT_PAGE_HTML = """<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="10">
<title>Iniciando a demo...</title>
<style>body { font-family: sans-serif; text-align: center; margin-top: 15%; }</style>
</head>
<body>
<h1>Iniciando a demo...</h1>
<p>O servico esta acordando, isso leva cerca de 1 a 2 minutos.</p>
<p>Esta pagina atualiza sozinha a cada 10 segundos.</p>
</body>
</html>"""


def wait_response():
    # Resposta usada tanto quando a Lambda acabou de pedir o start do
    # serviço quanto quando a task ainda está no warm-up.
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
        "body": WAIT_PAGE_HTML,
    }


def redirect_response(ip, port):
    # 302 para o IP público:porta da task já rodando e aquecida.
    return {
        "statusCode": 302,
        "headers": {"Location": f"http://{ip}:{port}"},
    }
