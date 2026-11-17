from uuid import UUID
from pydantic import BaseModel, Field, StrictBool, ConfigDict, AwareDatetime, model_validator, field_validator

class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class LoginInput(Input):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)

class RegisterInput(LoginInput):
    username: str = Field(min_length=3, max_length=100, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024)
    password_confirm: str = Field(min_length=1, max_length=1024)

    @field_validator('email')
    @classmethod
    def valid_email(cls, value):
        return ProfileInput.valid_email(value.strip()).lower()

    @model_validator(mode='after')
    def matching_passwords(self):
        if not self.password.strip() or self.password != self.password_confirm:
            raise ValueError('Mật khẩu không hợp lệ hoặc chưa khớp')
        return self


class HoldInput(Input):
    session_id: UUID
    seat_id: UUID

class CheckInInput(Input):
    ticket_code: str = Field(min_length=20, max_length=100)

class CheckinPolicyInput(Input):
    enabled: StrictBool
    close_mode: str | None = None
    closes_at: AwareDatetime | None = None


class RoomInput(Input):
    name: str = Field(min_length=1, max_length=120)

class SeatInput(Input):
    seat_code: str = Field(min_length=1, max_length=30)

class LabInput(Input):
    event_id: UUID | None = None
    room_id: UUID
    open_at: AwareDatetime
    close_at: AwareDatetime
    start_at: AwareDatetime
    end_at: AwareDatetime
    @model_validator(mode='after')
    def ordered(self):
        if not self.open_at < self.close_at <= self.start_at < self.end_at:
            raise ValueError('open_at < close_at <= start_at < end_at')
        return self

from typing import Literal
class MapElement(Input):
    id: UUID
    kind: Literal['seat','board','door','label']
    seat_id: UUID | None = None
    seat_code: str = Field(default='',max_length=30)
    x: int = Field(ge=0,le=39)
    y: int = Field(ge=0,le=39)
    width: int = Field(default=1,ge=1,le=40)
    height: int = Field(default=1,ge=1,le=40)
    label: str = Field(default='',max_length=120)
class MapInput(Input):
    revision: int = Field(ge=0)
    columns: int = Field(ge=1,le=40)
    rows: int = Field(ge=1,le=40)
    elements: list[MapElement] = Field(max_length=500)


class QueueInput(Input):
    """No client-supplied identity or admission capability."""
    pass


class EventScheduleInput(Input):
    open_at: AwareDatetime
    close_at: AwareDatetime
    start_at: AwareDatetime
    end_at: AwareDatetime

    @model_validator(mode='after')
    def ordered(self):
        if not self.open_at < self.close_at <= self.start_at < self.end_at:
            raise ValueError('Thời gian đăng ký hoặc diễn ra không hợp lệ')
        return self


class EventInput(Input):
    schedule: EventScheduleInput | None = None
    name: str = Field(min_length=1, max_length=100)
    session_type: Literal['exam', 'practice']
    description: str = Field(default='', max_length=10000)
    venue: str = Field(min_length=1, max_length=120)
    address: str = Field(default='', max_length=300)


class ProfileInput(Input):
    current_password: str | None = Field(default=None, max_length=1024)
    full_name: str = Field(default='', max_length=150)
    cccd: str = Field(default='', max_length=12)
    phone: str = Field(default='', max_length=30)
    email: str = Field(min_length=1, max_length=254)

    @field_validator('full_name')
    @classmethod
    def valid_name(cls,value):
        import unicodedata
        value=unicodedata.normalize('NFC',' '.join(value.split()))
        if value and (not any(c.isalpha() for c in value) or any(unicodedata.category(c).startswith('C') for c in value)):
            raise ValueError('Họ tên không hợp lệ')
        return value

    @field_validator('cccd')
    @classmethod
    def valid_cccd(cls,value):
        import re
        if value and not re.fullmatch(r'[0-9]{12}',value):raise ValueError('CCCD gồm 12 chữ số')
        return value

    @field_validator('phone')
    @classmethod
    def valid_phone(cls,value):
        import re
        value=re.sub(r'[ () .-]','',value)
        if value.startswith('+84'):value='0'+value[3:]
        if value and not re.fullmatch(r'0[0-9]{9}',value):raise ValueError('Số điện thoại không hợp lệ')
        return value

    @field_validator('email')
    @classmethod
    def valid_email(cls,value):
        import re
        if not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',value):raise ValueError('Email bắt buộc và phải đúng định dạng')
        return value
