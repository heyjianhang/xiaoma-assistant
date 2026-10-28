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


def merged_table_archive(*, deleted=True, continuation="第二项", bbox=None):
    header = "<tr><td>编号</td><td>材料</td></tr>"
    first = "<tr><td>01</td><td>第一项</td></tr>"
    second = f"<tr><td>02</td><td>{continuation}</td></tr>"
    full = f"<table>{header}{first}<tr><td>02</td><td>第二项</td></tr></table>"
    table_box = [10, 10, 90, 90]
    items = [
        {"type": "table", "table_body": full, "page_idx": 0, "bbox": [100, 100, 900, 900]},
        {
            "type": "table",
            "table_body": "",
            "img_path": "",
            "page_idx": 1,
            "bbox": bbox or [100, 100, 900, 900],
        },
    ]
    layout = {
        "pdf_info": [
            {
                "page_idx": 1,
                "page_size": [100, 100],
                "preproc_blocks": [
                    {
                        "type": "table",
                        "bbox": table_box,
                        "blocks": [
                            {
                                "type": "table_body",
                                "lines": [
                                    {
                                        "spans": [
                                            {
                                                "type": "table",
                                                "html": f"<table>{header}{second}</table>",
                                            }
                                        ]
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "para_blocks": [
                    {
                        "type": "table",
                        "bbox": table_box,
                        "blocks": [
                            {
                                "type": "table_body",
                                "lines": [],
                                "lines_deleted": deleted,
                            }
                        ],
                    }
                ],
            }
        ]
    }
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("result/document_content_list.json", json.dumps(items))
        archive.writestr("result/layout.json", json.dumps(layout))
    return stream.getvalue()


def test_confirmed_merged_table_keeps_full_content_and_both_page_regions():
    parsed = parse_archive(merged_table_archive(), "task")
    assert len(parsed.blocks) == 1
    table = parsed.blocks[0]
    assert table.markdown.count("第二项") == 1
    assert "第一项" in table.markdown
    assert [ref["page_index"] for ref in table.source_refs] == [0, 1]
    assert table.source_refs[1]["bbox"] == [100, 100, 900, 900]
    assert table.source_refs[1]["merged_table_parent"] == table.id
    assert parsed.pages == 2 and parsed.source_map_available


@pytest.mark.parametrize(
    "kwargs",
    [
        {"deleted": False},
        {"continuation": "不在合并正文里的第三项"},
        {"bbox": [500, 500, 600, 600]},
    ],
)
def test_unconfirmed_empty_table_is_not_silently_discarded(kwargs):
    with pytest.raises(IngestionError, match="表格缺少"):
        parse_archive(merged_table_archive(**kwargs), "task")
