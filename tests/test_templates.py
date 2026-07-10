from scripts.lambda_wake.templates import redirect_response, wait_response


def test_wait_response_is_200_html_with_refresh_meta():
    resp = wait_response()
    assert resp["statusCode"] == 200
    assert "refresh" in resp["body"]
    assert resp["headers"]["Content-Type"].startswith("text/html")


def test_redirect_response_points_to_task_ip_and_port():
    resp = redirect_response("1.2.3.4", 8501)
    assert resp["statusCode"] == 302
    assert resp["headers"]["Location"] == "http://1.2.3.4:8501"
