from dataclasses import dataclass
import os

@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL","postgresql://concilia:concilia@localhost:5432/concilia")
    minio_endpoint: str = os.getenv("MINIO_ENDPOINT","minio:9000")
    minio_bucket: str = os.getenv("MINIO_BUCKET","concilia-fase1")
    minio_access_key: str = os.getenv("MINIO_ACCESS_KEY","concilia")
    minio_secret_key: str = os.getenv("MINIO_SECRET_KEY","concilia123")
    minio_secure: bool = os.getenv("MINIO_SECURE","false").lower()=="true"
    parseo_api_url: str = os.getenv("PARSEO_API_URL","http://parseo:8081")
    page_size: int = int(os.getenv("PAGE_SIZE","30"))
    max_page_size: int = int(os.getenv("MAX_PAGE_SIZE","100"))

settings=Settings()
