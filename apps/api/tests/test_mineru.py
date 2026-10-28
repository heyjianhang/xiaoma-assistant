import io
import json
import zipfile

import httpx
import pytest
import respx

from xiaoma.errors import IngestionError
from xiaoma.ingestion.mineru import MinerUParser, parse_archive


def archive_bytes(items):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("result/document_content_list.json", json.dumps(items))
    return stream.getvalue()


@respx.mock
async def test_upload_poll_download_keeps_auth_off_signed_urls(provider_settings):
    base = provider_settings.mineru_base_url
    create = respx.post(f"{base}/api/v4/file-urls/batch").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "data": {"batch_id": "batch", "file_urls": ["https://signed.test/upload"]},
            },
        )
    )
    upload = respx.put("https://signed.test/upload").mock(return_value=httpx.Response(200))
    poll = respx.get(f"{base}/api/v4/extract-results/batch/batch").mock(
        side_effect=[
            httpx.Response(
                200, json={"code": 0, "data": {"extract_result": [{"state": "running"}]}}
            ),
            httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "extract_result": [
                            {
                                "state": "done",
                                "data_id": "doc",
                                "full_zip_url": "https://signed.test/result.zip",
                            }
                        ]
                    },
                },
            ),
        ]
    )
    download = respx.get("https://signed.test/result.zip").mock(
        return_value=httpx.Response(
            200,
            content=archive_bytes([{"type": "text", "text": "可检索正文", "page_idx": 0}]),
        )
    )
    parsed, _ = await MinerUParser(provider_settings).parse(b"%PDF-test", "doc")
    assert parsed.blocks[0].markdown == "可检索正文" and poll.call_count == 2
    assert create.calls.last.request.headers["Authorization"] == "Bearer mineru-test"
    assert "Authorization" not in upload.calls.last.request.headers
    assert "Authorization" not in download.calls.last.request.headers
    payload = json.loads(create.calls.last.request.content)
    assert payload["enable_table"] and payload["enable_formula"]


def test_missing_structure_and_table_body_fail_explicitly():
    with pytest.raises(IngestionError, match="表格缺少"):
        parse_archive(archive_bytes([{"type": "table", "img_path": "table.png"}]), "task")
    with pytest.raises(IngestionError, match="压缩包无效"):
        parse_archive(b"not zip", "task")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("full.md", "plain text is insufficient")
    with pytest.raises(IngestionError, match="结构化内容列表"):
        parse_archive(stream.getvalue(), "task")


def test_normalized_source_regions_are_preserved_and_invalid_boxes_disabled():
    items = [
        {"type": "text", "text": "退款时效", "page_idx": 1, "bbox": [75, 90, 850, 130]},
        {
            "type": "table",
            "table_body": "<table><tr><td>48小时</td></tr></table>",
            "page_idx": 1,
            "bbox": [70, 200, 900, 420],
        },
        {"type": "text", "text": "注：从验收开始", "page_idx": 1, "bbox": [70, 430, 900, 460]},
    ]
    parsed = parse_archive(archive_bytes(items), "task")
    assert parsed.source_map_available
    table = next(block for block in parsed.blocks if block.kind == "table")
    assert len(table.source_refs) == 2  # Table plus attached footnote, each keeps its own region.
    assert table.source_refs[0]["bbox"] == [70, 200, 900, 420]
    assert table.source_refs[1]["coordinate_space"] == "normalized_1000"
    for bbox in ([900, 90, 75, 130], [0, 0, 1001, 90], [0, 0, float("nan"), 90], [0, 0, 0, 0]):
        invalid = parse_archive(archive_bytes([dict(items[0], bbox=bbox)]), "task")
        assert not invalid.source_map_available
        assert "bbox" not in invalid.blocks[0].source_refs[0]
