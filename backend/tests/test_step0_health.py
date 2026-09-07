def test_healthz_ok(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["sap_mode"] == "mock"


def test_unknown_route_404(client):
    r = client.get("/no-such-route")
    assert r.status_code == 404
