from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def session_factory(url):
    return sessionmaker(create_engine(url, pool_pre_ping=True), expire_on_commit=False)
