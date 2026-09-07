from pydantic import BaseModel, Field


class UserOut(BaseModel):
    id: str
    role: str
    name: str
    phone: str | None = None
    email: str | None = None
    sap_customer_no: str | None = None
    staff_code: str | None = None
    branch_id: str | None = None
    tier: str | None = None
    is_guest: bool = False
    default_address: str | None = None
    default_postcode: str | None = None

    model_config = {"from_attributes": True}


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class RegisterIn(BaseModel):
    phone: str = Field(min_length=9, max_length=20)
    password: str = Field(min_length=4, max_length=72)
    name: str = Field(min_length=1, max_length=120)
    email: str | None = None


class LoginIn(BaseModel):
    identifier: str = Field(min_length=1, description="ลูกค้า: เบอร์โทร / อีเมล / เลขสมาชิก · พนักงาน: รหัสพนักงาน")
    password: str = Field(min_length=1)
    account_type: str = Field(default="customer", pattern="^(customer|staff)$")


class RefreshIn(BaseModel):
    refresh_token: str


class OtpRequestIn(BaseModel):
    phone: str = Field(min_length=9, max_length=20)


class OtpVerifyIn(BaseModel):
    phone: str
    code: str = Field(min_length=4, max_length=8)
    name: str | None = None
