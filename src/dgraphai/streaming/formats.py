"""
Data stream format serializers.

Supported output formats:
  jsonl        — line-delimited JSON (Hugging Face, OpenAI fine-tuning)
  parquet      — columnar binary (PyArrow, Spark, DuckDB)
  webdataset   — tar-based shards (LAION, OpenCLIP, multimodal training)
  arrow        — raw Arrow IPC stream (zero-copy for PyTorch/JAX)
  csv          — tabular text (sklearn, Excel, anything)

All formats stream from an async generator — no full materialization required.
Memory usage is O(batch_size), not O(dataset_size).
"""
from __future__ import annotations

import io
import json
import struct
import tarfile
from collections.abc import AsyncIterator
from typing import Any


async def stream_jsonl(
    rows: AsyncIterator[dict[str, Any]],
) -> AsyncIterator[bytes]:
    """
    Stream rows as JSONL (newline-delimited JSON).
    Standard format for LLM fine-tuning datasets (OpenAI, Anthropic, HF).
    """
    async for row in rows:
        yield (json.dumps(row, ensure_ascii=False) + "\n").encode()


async def stream_arrow(
    rows: AsyncIterator[dict[str, Any]],
    batch_size: int = 1000,
) -> AsyncIterator[bytes]:
    """
    Stream rows as Arrow IPC record batches.
    Zero-copy deserialization in PyTorch/JAX via pyarrow.
    Client usage:
      reader = pa.ipc.open_stream(response_body)
      for batch in reader: df = batch.to_pandas()
    """
    import pyarrow as pa

    batch: list[dict] = []
    schema: pa.Schema | None = None
    sink = io.BytesIO()
    writer: Any = None

    async for row in rows:
        batch.append(row)
        if len(batch) >= batch_size:
            table = pa.Table.from_pylist(batch)
            if writer is None:
                schema = table.schema
                writer = pa.ipc.new_stream(sink, schema)
                # Write schema message
                sink.seek(0)
                yield sink.read()
                sink.seek(0)
                sink.truncate()
            writer.write_table(table)
            sink.seek(0)
            yield sink.read()
            sink.seek(0)
            sink.truncate()
            batch = []

    if batch:
        table = pa.Table.from_pylist(batch)
        if writer is None:
            schema = table.schema
            sink2  = io.BytesIO()
            writer = pa.ipc.new_stream(sink2, schema)
            writer.write_table(table)
            writer.close()
            sink2.seek(0)
            yield sink2.read()
        else:
            writer.write_table(table)
            sink.seek(0)
            yield sink.read()

    if writer:
        writer.close()
        sink.seek(0)
        remaining = sink.read()
        if remaining:
            yield remaining


async def stream_parquet(
    rows: AsyncIterator[dict[str, Any]],
    batch_size: int = 10_000,
) -> AsyncIterator[bytes]:
    """
    Stream rows as Parquet row groups.
    Each chunk is a valid Parquet file fragment — client reassembles.
    For single-file output, use stream_parquet_file() instead.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    batch: list[dict] = []
    async for row in rows:
        batch.append(row)
        if len(batch) >= batch_size:
            buf = io.BytesIO()
            table = pa.Table.from_pylist(batch)
            pq.write_table(table, buf)
            buf.seek(0)
            yield buf.read()
            batch = []

    if batch:
        buf = io.BytesIO()
        table = pa.Table.from_pylist(batch)
        pq.write_table(table, buf)
        buf.seek(0)
        yield buf.read()


async def stream_webdataset(
    rows: AsyncIterator[dict[str, Any]],
    shard_size: int = 1000,
) -> AsyncIterator[bytes]:
    """
    Stream rows as WebDataset format (tar shards).
    Used by LAION, OpenCLIP, DataComp for large-scale vision training.
    Each sample becomes a tar entry: {key}.json

    Client usage (with webdataset library):
      ds = wds.WebDataset("pipe:curl http://dgraphai/stream/...").decode()
    """
    buf  = io.BytesIO()
    tar  = tarfile.open(fileobj=buf, mode="w|")
    count = 0
    shard_index = 0

    async for row in rows:
        sample_key = row.get("id", f"{shard_index:06d}_{count:06d}")
        json_bytes = json.dumps(row, ensure_ascii=False).encode()

        info = tarfile.TarInfo(name=f"{sample_key}.json")
        info.size = len(json_bytes)
        tar.addfile(info, io.BytesIO(json_bytes))
        count += 1

        if count % shard_size == 0:
            tar.close()
            buf.seek(0)
            yield buf.read()
            buf = io.BytesIO()
            tar = tarfile.open(fileobj=buf, mode="w|")
            shard_index += 1

    tar.close()
    buf.seek(0)
    data = buf.read()
    if data:
        yield data


async def stream_csv(
    rows: AsyncIterator[dict[str, Any]],
) -> AsyncIterator[bytes]:
    """Stream rows as CSV. Emits header on first row."""
    import csv

    header_written = False
    buf = io.StringIO()

    async for row in rows:
        if not header_written:
            writer = csv.DictWriter(buf, fieldnames=list(row.keys()))
            writer.writeheader()
            header_written = True
        else:
            writer = csv.DictWriter(buf, fieldnames=list(row.keys()))

        writer.writerow(row)
        buf.seek(0)
        yield buf.read().encode()
        buf.seek(0)
        buf.truncate()
