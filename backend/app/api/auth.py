from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginIn, OtpRequestIn, OtpVerifyIn, RefreshIn, RegisterIn, TokenPair, UserOut
from app.services import auth_service

router = APIRouter(tags=["auth"])


@router.post("/auth/register", response_model=TokenPair, status_code=201)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    return auth_service.register(db, body.phone, body.password, body.name, body.email, request)


@router.post("/auth/login", response_model=TokenPair)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    return auth_service.login(db, body.identifier, body.password, body.account_type, request)


@router.post("/auth/refresh", response_model=TokenPair)
def refresh(body: RefreshIn, request: Request, db: Session = Depends(get_db)):
    return auth_service.refresh(db, body.refresh_token, request)


@router.post("/auth/logout", status_code=204)
def logout(body: RefreshIn, db: Session = Depends(get_db)):
    auth_service.logout(db, body.refresh_token)
    return None


@router.post("/auth/otp/request")
def otp_request(body: OtpRequestIn, db: Session = Depends(get_db)):
    return auth_service.otp_request(db, body.phone)


@router.post("/auth/otp/verify", response_model=TokenPair)
def otp_verify(body: OtpVerifyIn, request: Request, db: Session = Depends(get_db)):
    return auth_service.otp_verify(db, body.phone, body.code, body.name, request)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
