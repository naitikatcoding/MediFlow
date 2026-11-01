import app.models
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.organization import Facility
from app.models.product import Product
from app.services.seed_service import seed_demo_data_if_empty


def test_demo_bootstrap_seeds_only_an_empty_database():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        assert seed_demo_data_if_empty(session) is True
        assert session.query(Facility).count() == 4
        assert session.query(Product).count() == 16

        assert seed_demo_data_if_empty(session) is False
        assert session.query(Facility).count() == 4
        assert session.query(Product).count() == 16
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
