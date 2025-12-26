"""
Artifact storage backend for SSR Studio.

Supports local filesystem and S3-compatible object storage.
"""

import io
import tarfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import AsyncIterator
from uuid import UUID

import aiofiles
import aiofiles.os

from ssr_studio.config import settings


class StorageBackend(ABC):
    """Abstract base class for storage backends."""
    
    @abstractmethod
    async def write(self, key: str, content: str | bytes) -> str:
        """Write content to storage and return the reference."""
        pass
    
    @abstractmethod
    async def read(self, ref: str) -> str:
        """Read content from storage."""
        pass
    
    @abstractmethod
    async def read_bytes(self, ref: str) -> bytes:
        """Read binary content from storage."""
        pass
    
    @abstractmethod
    async def exists(self, ref: str) -> bool:
        """Check if a reference exists."""
        pass
    
    @abstractmethod
    async def delete(self, ref: str) -> None:
        """Delete content from storage."""
        pass
    
    @abstractmethod
    async def list_keys(self, prefix: str) -> list[str]:
        """List all keys with the given prefix."""
        pass
    
    async def write_artifact_files(
        self,
        artifact_id: UUID,
        test_script: str,
        test_files: list[str],
        test_parser: str,
        bug_inject_diff: str,
        test_weaken_diff: str,
    ) -> dict[str, str]:
        """Write all artifact files and return references."""
        prefix = f"artifacts/{artifact_id}"
        
        refs = {}
        refs["test_script_ref"] = await self.write(f"{prefix}/test_script.sh", test_script)
        refs["test_files_ref"] = await self.write(f"{prefix}/test_files.txt", "\n".join(test_files))
        refs["test_parser_ref"] = await self.write(f"{prefix}/test_parser.py", test_parser)
        refs["bug_inject_diff_ref"] = await self.write(f"{prefix}/bug_inject.diff", bug_inject_diff)
        refs["test_weaken_diff_ref"] = await self.write(f"{prefix}/test_weaken.diff", test_weaken_diff)
        
        return refs
    
    async def get_artifact_tarball(self, artifact_id: UUID) -> AsyncIterator[bytes]:
        """Create a tarball of all artifact files."""
        prefix = f"artifacts/{artifact_id}"
        
        files = {
            "test_script.sh": await self.read(f"{prefix}/test_script.sh"),
            "test_files.txt": await self.read(f"{prefix}/test_files.txt"),
            "test_parser.py": await self.read(f"{prefix}/test_parser.py"),
            "bug_inject.diff": await self.read(f"{prefix}/bug_inject.diff"),
            "test_weaken.diff": await self.read(f"{prefix}/test_weaken.diff"),
        }
        
        # Create in-memory tarball
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            for name, content in files.items():
                data = content.encode("utf-8") if isinstance(content, str) else content
                info = tarfile.TarInfo(name=f"artifact/{name}")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        
        buffer.seek(0)
        
        # Yield chunks for streaming
        chunk_size = 8192
        while chunk := buffer.read(chunk_size):
            yield chunk


class LocalStorage(StorageBackend):
    """Local filesystem storage backend."""
    
    def __init__(self, base_path: Path | None = None):
        self.base_path = base_path or settings.storage_path
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    def _get_path(self, key: str) -> Path:
        """Get the full path for a key."""
        return self.base_path / key
    
    async def write(self, key: str, content: str | bytes) -> str:
        """Write content to local filesystem."""
        path = self._get_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        mode = "w" if isinstance(content, str) else "wb"
        async with aiofiles.open(path, mode) as f:
            await f.write(content)
        
        return str(path)
    
    async def read(self, ref: str) -> str:
        """Read content from local filesystem."""
        path = Path(ref) if ref.startswith("/") else self._get_path(ref)
        
        async with aiofiles.open(path, "r") as f:
            return await f.read()
    
    async def read_bytes(self, ref: str) -> bytes:
        """Read binary content from local filesystem."""
        path = Path(ref) if ref.startswith("/") else self._get_path(ref)
        
        async with aiofiles.open(path, "rb") as f:
            return await f.read()
    
    async def exists(self, ref: str) -> bool:
        """Check if a file exists."""
        path = Path(ref) if ref.startswith("/") else self._get_path(ref)
        return await aiofiles.os.path.exists(path)
    
    async def delete(self, ref: str) -> None:
        """Delete a file."""
        path = Path(ref) if ref.startswith("/") else self._get_path(ref)
        if await aiofiles.os.path.exists(path):
            await aiofiles.os.remove(path)
    
    async def list_keys(self, prefix: str) -> list[str]:
        """List all files with the given prefix."""
        path = self._get_path(prefix)
        if not path.exists():
            return []
        
        keys = []
        for file_path in path.rglob("*"):
            if file_path.is_file():
                keys.append(str(file_path.relative_to(self.base_path)))
        
        return keys


class S3Storage(StorageBackend):
    """S3-compatible object storage backend."""
    
    def __init__(self):
        import boto3
        from botocore.config import Config
        
        config = Config(
            connect_timeout=5,
            read_timeout=30,
            retries={"max_attempts": 3},
        )
        
        kwargs = {
            "config": config,
        }
        
        if settings.s3_endpoint_url:
            kwargs["endpoint_url"] = settings.s3_endpoint_url
        
        if settings.s3_access_key and settings.s3_secret_key:
            kwargs["aws_access_key_id"] = settings.s3_access_key.get_secret_value()
            kwargs["aws_secret_access_key"] = settings.s3_secret_key.get_secret_value()
        
        self.client = boto3.client("s3", **kwargs)
        self.bucket = settings.s3_bucket
    
    async def write(self, key: str, content: str | bytes) -> str:
        """Write content to S3."""
        import asyncio
        
        body = content.encode("utf-8") if isinstance(content, str) else content
        
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=body,
        )
        
        return f"s3://{self.bucket}/{key}"
    
    async def read(self, ref: str) -> str:
        """Read content from S3."""
        content = await self.read_bytes(ref)
        return content.decode("utf-8")
    
    async def read_bytes(self, ref: str) -> bytes:
        """Read binary content from S3."""
        import asyncio
        
        # Parse S3 URI or use as key
        if ref.startswith("s3://"):
            parts = ref[5:].split("/", 1)
            bucket = parts[0]
            key = parts[1] if len(parts) > 1 else ""
        else:
            bucket = self.bucket
            key = ref
        
        response = await asyncio.to_thread(
            self.client.get_object,
            Bucket=bucket,
            Key=key,
        )
        
        return response["Body"].read()
    
    async def exists(self, ref: str) -> bool:
        """Check if an object exists in S3."""
        import asyncio
        from botocore.exceptions import ClientError
        
        if ref.startswith("s3://"):
            parts = ref[5:].split("/", 1)
            bucket = parts[0]
            key = parts[1] if len(parts) > 1 else ""
        else:
            bucket = self.bucket
            key = ref
        
        try:
            await asyncio.to_thread(
                self.client.head_object,
                Bucket=bucket,
                Key=key,
            )
            return True
        except ClientError:
            return False
    
    async def delete(self, ref: str) -> None:
        """Delete an object from S3."""
        import asyncio
        
        if ref.startswith("s3://"):
            parts = ref[5:].split("/", 1)
            bucket = parts[0]
            key = parts[1] if len(parts) > 1 else ""
        else:
            bucket = self.bucket
            key = ref
        
        await asyncio.to_thread(
            self.client.delete_object,
            Bucket=bucket,
            Key=key,
        )
    
    async def list_keys(self, prefix: str) -> list[str]:
        """List all objects with the given prefix."""
        import asyncio
        
        response = await asyncio.to_thread(
            self.client.list_objects_v2,
            Bucket=self.bucket,
            Prefix=prefix,
        )
        
        return [obj["Key"] for obj in response.get("Contents", [])]


# Global storage instance
_storage: StorageBackend | None = None


def get_storage() -> StorageBackend:
    """Get the configured storage backend."""
    global _storage
    
    if _storage is None:
        if settings.storage_backend == "s3":
            _storage = S3Storage()
        else:
            _storage = LocalStorage()
    
    return _storage
