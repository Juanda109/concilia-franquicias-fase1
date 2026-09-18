import io
import logging
import os

import boto3

from domain.genai.filesystem import AbstractFileSystemUnitOfWork
from infrastructure.core.config import genai_config

log = logging.getLogger(__name__)


class S3FileSystemUnitOfWork(AbstractFileSystemUnitOfWork):
    def __init__(self, route: str = genai_config.GENAI_S3_BUCKET_NAME):
        self._route = route
        log.debug("S3: Using AWS S3")
        self._s3_client = boto3.client("s3")

    def get_file(self, file: str) -> bytes:
        """Get file content from S3 bucket

        Args:
            file (str): S3 Key name

        Returns:
            bytes: The file content in bytes

        Raises:
            e: The key does not exist in the bucket
        """
        file_content = None
        try:
            response = self._s3_client.get_object(Bucket=self._route, Key=file)

            # print(response["ContentType"])
            file_content = response["Body"].read()
        except Exception as e:
            log.error(e)
            log.error(
                f"Error getting object {self._route} from bucket {file}."
                f" Make sure they exist and "
                f"your bucket is in the same region as this function."
            )
            raise e

        return file_content

    def upload_file(self, file_route: str, name: str = None) -> bool:
        """Upload a file to an S3 bucket

        Args:
            file_route (str): File (path) to upload
            name (str): S3 object name. If not specified then file_name is used

        Returns:
            bool: True if file was uploaded, else False
        """

        # If S3 object_name was not specified, use file_name
        if name is None:
            name = os.path.basename(file_route)

        # Upload the file
        try:
            self._s3_client.upload_file(file_route, self._route, name)
        except Exception as e:
            log.error(e)
            return False

        return True

    def create_text_file(self, text: str, file: str, encoding: str = "utf-8") -> bool:
        """Upload a text file to an S3 bucket with the given text

        Args:
            text (str): Text content to upload
            file (str): S3 object name
            encoding (str): Encoding of the text. Default is 'utf-8'

        Returns:
            bool: True if file was uploaded, else False
        """

        # Encode text to bytes
        file_content = io.BytesIO(text.encode(encoding))

        # Upload the file
        try:
            self._s3_client.upload_fileobj(file_content, self._route, file)
        except Exception as e:
            log.error(e)
            return False

        return True

    def list_folder(self, prefix: str) -> list:
        """List all objects in a folder in an S3 bucket (not recursive)

        Args:
            prefix (str): Folder name. Ex: 'myfolder/'

        Returns:
            list: List of objects (keys) in the folder (up to 1000)
        """
        objects = []
        try:
            response = self._s3_client.list_objects_v2(
                Bucket=self._route, Prefix=prefix, Delimiter="/"
            )
            if "Contents" in response:
                objects = [
                    content["Key"]
                    for content in response["Contents"]
                    if content["Key"] != prefix
                ]
        except Exception as e:
            log.error(e)
            log.error(
                f"Error listing objects in bucket {self._route}. "
                f"Make sure it exists and your bucket "
                f"is in the same region as this function."
            )
            raise e

        return objects

    def move_file(self, old_file: str, new_file: str, new_route: str = None) -> bool:
        """Move a file from one location to another
        Args:
            old_file (str): Old key name
            new_file (str): New key name
            new_route (str): New route name
        Returns:
            bool: True if file was moved, else False
        """
        try:
            if new_route is None:
                new_route = self._route

            self._s3_client.copy_object(
                Bucket=new_route,
                CopySource={"Bucket": self._route, "Key": old_file},
                Key=new_file,
            )
            self._s3_client.delete_object(Bucket=self._route, Key=old_file)
        except Exception as e:
            log.error(e)
            return False

        return True

    def delete_file(self, file: str) -> bool:
        """Delete a file from S3 bucket

        Args:
            file (str): Key name

        Returns:
            bool: True if file was deleted, else False
        """
        try:
            self._s3_client.delete_object(Bucket=self._route, Key=file)
        except Exception as e:
            log.error(e)
            return False

        return True

    def move_route(self, route: str):
        self._route = route
