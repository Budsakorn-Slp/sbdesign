from app.db.session import SessionLocal
from app.seed import seed_users


def ensure_seed() -> None:
    with SessionLocal() as db:
        seed_users(db)


def login(client, identifier: str, password: str = "1234", account_type: str = "customer") -> dict:
    r = client.post("/auth/login", json={"identifier": identifier, "password": password, "account_type": account_type})
    assert r.status_code == 200, r.text
    return r.json()


def auth_headers(client, identifier: str, account_type: str = "customer") -> dict:
    tok = login(client, identifier, account_type=account_type)
    return {"Authorization": "Bearer " + tok["access_token"]}
