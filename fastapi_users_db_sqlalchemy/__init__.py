"""FastAPI Users database adapter for SQLAlchemy."""
import uuid
from typing import Any, Dict, Generic, Optional, Type, TypeVar

from fastapi_users.db.base import BaseUserDatabase
from fastapi_users.models import ID, OAP
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.sql import Select

from fastapi_users_db_sqlalchemy.generics import GUID

__version__ = "4.0.0"

UUID_ID = uuid.UUID


class SQLAlchemyBaseUserTable(Generic[ID]):
    """Base SQLAlchemy users table definition."""

    __tablename__ = "user"

    id: ID
    email: str = Column(String(length=320), unique=True, index=True, nullable=False)
    hashed_password: str = Column(String(length=1024), nullable=False)
    is_active: bool = Column(Boolean, default=True, nullable=False)
    is_superuser: bool = Column(Boolean, default=False, nullable=False)
    is_verified: bool = Column(Boolean, default=False, nullable=False)


UP_SQLALCHEMY = TypeVar("UP_SQLALCHEMY", bound=SQLAlchemyBaseUserTable)


class SQLAlchemyBaseUserTableUUID(SQLAlchemyBaseUserTable[UUID_ID]):
    id: UUID_ID = Column(GUID, primary_key=True, default=uuid.uuid4)


class SQLAlchemyBaseOAuthAccountTable(Generic[ID]):
    """Base SQLAlchemy OAuth account table definition."""

    __tablename__ = "oauth_account"

    id: ID
    oauth_name: str = Column(String(length=100), index=True, nullable=False)
    access_token: str = Column(String(length=1024), nullable=False)
    expires_at: Optional[int] = Column(Integer, nullable=True)
    refresh_token: Optional[str] = Column(String(length=1024), nullable=True)
    account_id: str = Column(String(length=320), index=True, nullable=False)
    account_email: str = Column(String(length=320), nullable=False)


class SQLAlchemyBaseOAuthAccountTableUUID(SQLAlchemyBaseOAuthAccountTable[UUID_ID]):
    id: UUID_ID = Column(GUID, primary_key=True, default=uuid.uuid4)

    @declared_attr
    def user_id(cls):
        return Column(GUID, ForeignKey("user.id", ondelete="cascade"), nullable=False)


class SQLAlchemyUserDatabase(
    Generic[UP_SQLALCHEMY, ID], BaseUserDatabase[UP_SQLALCHEMY, ID]
):
    """
    Database adapter for SQLAlchemy.

    :param session: SQLAlchemy session instance.
    :param user_table: SQLAlchemy user model.
    :param oauth_account_table: Optional SQLAlchemy OAuth accounts model.
    """

    session: AsyncSession
    user_table: Type[UP_SQLALCHEMY]
    oauth_account_table: Optional[Type[SQLAlchemyBaseOAuthAccountTable]]

    def __init__(
        self,
        session: AsyncSession,
        user_table: Type[UP_SQLALCHEMY],
        oauth_account_table: Optional[Type[SQLAlchemyBaseOAuthAccountTable]] = None,
    ):
        self.session = session
        self.user_table = user_table
        self.oauth_account_table = oauth_account_table

    async def get(self, id: ID) -> Optional[UP_SQLALCHEMY]:
        statement = select(self.user_table).where(self.user_table.id == id)
        return await self._get_user(statement)

    async def get_by_email(self, email: str) -> Optional[UP_SQLALCHEMY]:
        statement = select(self.user_table).where(
            func.lower(self.user_table.email) == func.lower(email)
        )
        return await self._get_user(statement)

    async def get_by_oauth_account(
        self, oauth: str, account_id: str
    ) -> Optional[UP_SQLALCHEMY]:
        if self.oauth_account_table is None:
            raise NotImplementedError()

        statement = (
            select(self.user_table)
            .join(self.oauth_account_table)
            .where(self.oauth_account_table.oauth_name == oauth)
            .where(self.oauth_account_table.account_id == account_id)
        )
        return await self._get_user(statement)

    async def create(self, create_dict: Dict[str, Any]) -> UP_SQLALCHEMY:
        user = self.user_table(**create_dict)
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update(
        self, user: UP_SQLALCHEMY, update_dict: Dict[str, Any]
    ) -> UP_SQLALCHEMY:
        for key, value in update_dict.items():
            setattr(user, key, value)
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def delete(self, user: UP_SQLALCHEMY) -> None:
        await self.session.delete(user)
        await self.session.commit()

    async def add_oauth_account(
        self, user: UP_SQLALCHEMY, create_dict: Dict[str, Any]
    ) -> UP_SQLALCHEMY:
        if self.oauth_account_table is None:
            raise NotImplementedError()

        oauth_account = self.oauth_account_table(**create_dict)
        self.session.add(oauth_account)
        user.oauth_accounts.append(oauth_account)  # type: ignore
        self.session.add(user)

        await self.session.commit()
        await self.session.refresh(user)

        return user

    async def update_oauth_account(
        self, user: UP_SQLALCHEMY, oauth_account: OAP, update_dict: Dict[str, Any]
    ) -> UP_SQLALCHEMY:
        if self.oauth_account_table is None:
            raise NotImplementedError()

        for key, value in update_dict.items():
            setattr(oauth_account, key, value)
        self.session.add(oauth_account)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def _get_user(self, statement: Select) -> Optional[UP_SQLALCHEMY]:
        results = await self.session.execute(statement)
        user = results.first()
        if user is None:
            return None

        return user[0]
