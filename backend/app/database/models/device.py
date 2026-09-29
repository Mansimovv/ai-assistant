from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base, TimestampMixin


class Device(TimestampMixin, Base):
    __tablename__ = "devices"

    # Chosen by the device agent, e.g. "macbook-pro".
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(20))  # a DeviceType value
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
