from dataclasses import dataclass
import os

@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL","postgresql://concilia:concilia@localhost:5432/concilia")
    minio_endpoint: str = os.getenv("MINIO_ENDPOINT","minio:9000")
    minio_bucket: str = os.getenv("MINIO_BUCKET","concilia-fase1")
    page_size: int = int(os.getenv("PAGE_SIZE","30"))
    max_page_size: int = int(os.getenv("MAX_PAGE_SIZE","100"))
    incoming_dir: str = os.getenv("INCOMING_DIR","data/incoming")

settings=Settings()
