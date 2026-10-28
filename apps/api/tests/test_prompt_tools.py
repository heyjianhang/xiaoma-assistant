import json
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from xiaoma.agent.builder import build_system_prompt
from xiaoma.agent.routes import ToolAccess
from xiaoma.agent.skill_packages import export_package, make_package, read_package
from xiaoma.agent.sql import validate_sql
from xiaoma.agent.tools import SQL_TOOL_NAMES, allowed_names, build_tools
from xiaoma.settings import ROOT


def doc(document, chunk, content):
    return {
        "id": chunk,
        "page_content": content,
        "metadata": {
            "document_id": document,
            "source": "规则.pdf",
            "revision": 1,
            "section_path": ["计时规则"],
            "source_refs": [{"page_index": 1}],
        },
    }


@pytest.fixture
def harness(monkeypatch):
    from xiaoma.agent import tools as module

    result = {
        "id": "current-result",
        "columns": ["数量", "比例"],
        "rows": [{"数量": 0, "比例": None}],
        "scope": "当前查询",
        "truncated": False,
    }
    session = SimpleNamespace(results={"current-result": result})
    monkeypatch.setattr(module, "SqlSession", lambda business: session)
    db = SimpleNamespace(search=AsyncMock(return_value=[]))
    events = []
    tools = build_tools(
        db, None, ToolAccess(), None, SimpleNamespace(assert_active=AsyncMock()), [], events.append
    )
    return SimpleNamespace(db=db, tools={t.name: t for t in tools}, events=events, session=session)


async def test_citations_stay_stable_when_followup_search_repeats_a_chunk(harness):
    document, first, second = str(uuid4()), str(uuid4()), str(uuid4())
    a, b = doc(document, first, "完整表格"), doc(document, second, "附注")
    harness.db.search.side_effect = [[a], [a, b]]
    tool = harness.tools["search_knowledge"]
    initial = (await tool.ainvoke({"query": "计时"}))["items"][0]
    followup = (await tool.ainvoke({"query": "附注", "document_id": document}))["items"]
    assert followup[0] == initial
    assert followup[1]["evidence_id"] != initial["evidence_id"]
    assert followup[1]["citation_markdown"] == "[2]"
    assert len([e for e in harness.events if e["type"] == "citations"][-1]["citations"]) == 2
    harness.db.search.assert_awaited_with("附注", 5, document)


async def test_targeted_search_does_not_guess_documents_from_another_run(harness):
    with pytest.raises(ValueError, match="先全库检索"):
        await harness.tools["search_knowledge"].ainvoke(
            {"query": "退款", "document_id": str(uuid4())}
        )
    harness.db.search.assert_not_awaited()


async def test_schema_batch_constraint_is_in_the_model_contract(harness):
    tool = harness.tools["get_table_schema"]
    schema = tool.args_schema.model_json_schema()["properties"]["tables"]
    assert schema["minItems"] == 1 and schema["maxItems"] == 3
    with pytest.raises(ValidationError):
        await tool.ainvoke({"tables": ["a", "b", "c", "d"]})


async def test_metrics_preserve_zero_and_null_but_require_one_numeric_row(harness):
    tool = harness.tools["render_chart"]
    await tool.ainvoke({"result_id": "current-result", "view": "metrics", "title": "指标"})
    payload = harness.events[-1]["slot"]["payload"]
    assert payload["result"]["rows"] == [{"数量": 0, "比例": None}]
    harness.session.results["current-result"]["rows"].append({"数量": 2, "比例": 1})
    with pytest.raises(ValueError, match="一行聚合"):
        await tool.ainvoke({"result_id": "current-result", "view": "metrics", "title": "指标"})
    with pytest.raises(ValueError, match="本轮查询结果"):
        await tool.ainvoke({"result_id": "historical-result", "view": "metrics", "title": "指标"})


@pytest.mark.parametrize(
    "kind,comparable,verdict",
    [
        ("missing_data", False, "无法判定"),
        ("execution_deviation", True, "存在执行偏差"),
        ("consistent", True, "核验一致"),
    ],
)
async def test_review_categories_keep_missing_data_distinct_from_proven_deviation(
    harness,
    kind,
    comparable,
    verdict,
):
    document, chunk = str(uuid4()), str(uuid4())
    harness.db.search.return_value = [doc(document, chunk, "必须有验收时间")]
    evidence = (await harness.tools["search_knowledge"].ainvoke({"query": "验收"}))["items"][0]
    request = dict(
        kind=kind,
        comparable=comparable,
        title="时效核验",
        summary="依据记录核验",
        evidence_ids=[evidence["evidence_id"]],
        result_id="current-result",
        checks=["已查记录"],
        limitations=["遵循规则"],
    )
    result = await harness.tools["present_evidence_review"].ainvoke(request)
    assert result["status"] == verdict
    assert harness.events[-1]["slot"]["payload"]["verdict"] == verdict
    if kind == "execution_deviation":
        pending = await harness.tools["present_evidence_review"].ainvoke(
            {**request, "comparable": False}
        )
        assert pending["status"] == "不可直接比较"
    else:
        with pytest.raises(ValueError):
            await harness.tools["present_evidence_review"].ainvoke(
                {**request, "comparable": not comparable}
            )
    with pytest.raises(ValueError, match="本轮成功执行"):
        await harness.tools["present_evidence_review"].ainvoke(
            {**request, "result_id": "other-run"}
        )


def test_skill_loading_is_progressive_and_selected_resources_remain_versioned():
    skills = [
        dict(
            id="first",
            name="技能甲",
            description="甲类工作",
            revision=2,
            body="SELECT_SECRET_BODY_A",
            manifest={"files": [{"path": "references/a.md"}]},
        ),
        dict(
            id="second",
            name="技能乙",
            description="乙类工作",
            revision=7,
            body="SELECT_SECRET_BODY_B",
            manifest={},
        ),
    ]
    prompt = build_system_prompt(skills, ["first"], ToolAccess(knowledge=False, data=True))
    assert "SELECT_SECRET_BODY_B" not in prompt
    selected = json.loads(prompt.split("<selected_skills>\n")[1].split("\n</selected_skills>")[0])
    assert selected == [
        dict(
            id="first",
            revision=2,
            instructions="SELECT_SECRET_BODY_A",
            files=[{"path": "references/a.md"}],
        )
    ]
    assert "SELECT_SECRET_BODY_A" not in build_system_prompt(skills, [], ToolAccess())


def test_builtin_packages_preserve_valid_relative_references_and_tool_dependencies():
    names = allowed_names(ToolAccess())
    for path in (ROOT / "skills").glob("*/SKILL.md"):
        files = {
            p.relative_to(path.parent).as_posix(): p.read_bytes()
            for p in path.parent.rglob("*")
            if p.is_file()
        }
        package = make_package(files, "builtin")
        restored = read_package(export_package(package))
        assert restored["manifest"]["sha256"] == package["manifest"]["sha256"]
        dependencies = package["manifest"]["frontmatter"]["metadata"][
            "xiaoma-required-tools"
        ].split()
        assert set(dependencies).issubset(names)
        for target in re.findall(r"\]\(([^)]+)\)", package["body"]):
            assert target in files
    assert not SQL_TOOL_NAMES.intersection(allowed_names(ToolAccess(data=False)))
    assert "present_evidence_review" not in allowed_names(ToolAccess(knowledge=False))


def test_unlinked_column_diagnostic_is_actionable_and_sql_remains_select_only():
    context = {"tables": {"orders": ["order_id"]}}
    with pytest.raises(ValueError, match="paid_at"):
        validate_sql("SELECT o.paid_at FROM orders o", context, "business_v1")
    assert "COUNT(*)" in validate_sql("SELECT COUNT(*) AS n FROM orders", context, "business_v1")
    with pytest.raises(ValueError, match="单条SELECT"):
        validate_sql("DELETE FROM orders", context, "business_v1")
