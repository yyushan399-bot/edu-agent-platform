"""teacher_pbl_finalize 单元测试。"""

from backend.services.teacher_pbl_finalize import extract_failed_dimension_views


def _sample_result() -> dict:
    return {
        "dimension_summary": [
            {
                "dimension_key": "problem_posing",
                "dimension_name": "问题提出",
                "primary_indicator": "创造性思维",
                "agent_key": "creativity",
                "mean": 3.2,
                "summary_comment": "问题较常规",
            },
            {
                "dimension_key": "plan_novelty",
                "dimension_name": "方案新颖性",
                "primary_indicator": "创造性思维",
                "agent_key": "creativity",
                "mean": 4.1,
                "summary_comment": "方案有一定新意",
            },
            {
                "dimension_key": "evidence_quality",
                "dimension_name": "证据质量",
                "primary_indicator": "批判性思维",
                "agent_key": "critical",
                "mean": 2.5,
                "summary_comment": "证据不足",
            },
        ],
        "internal_audit": {
            "failed_parts": ["creativity", "critical"],
            "creativity": {
                "audit_passed": False,
                "max_review_rounds_reached": True,
                "failed_dimension_keys": ["problem_posing"],
            },
            "critical": {
                "audit_passed": False,
                "max_review_rounds_reached": True,
                "failed_dimension_keys": ["evidence_quality"],
            },
            "problemsolving": {"audit_passed": True, "failed_dimension_keys": []},
        },
    }


def test_extract_failed_dimension_views_only_failed_subdimensions() -> None:
    views = extract_failed_dimension_views(_sample_result())
    names = {v["dimension_name"] for v in views}
    assert names == {"问题提出", "证据质量"}
    assert len(views) == 2
    assert all(v["audit_failed"] is True for v in views)


def test_is_teacher_audit_passed_at_max_rounds_with_failures() -> None:
    from backend.services.teacher_pbl_finalize import is_teacher_audit_passed

    result = _sample_result()
    result["internal_audit"]["creativity"]["max_review_rounds_reached"] = True
    result["internal_audit"]["critical"]["max_review_rounds_reached"] = True
    assert is_teacher_audit_passed(
        result=result,
        teacher_reviewed=False,
        max_review_rounds_reached=True,
    ) is False


def test_is_teacher_audit_passed_after_teacher_review() -> None:
    from backend.services.teacher_pbl_finalize import is_teacher_audit_passed

    assert is_teacher_audit_passed(
        result=_sample_result(),
        teacher_reviewed=True,
        max_review_rounds_reached=True,
    ) is True


def test_sync_leader_display_payload_recomputes_primary() -> None:
    from backend.services.teacher_pbl_finalize import sync_leader_display_payload

    result = {
        "teacher_modified": True,
        "teacher_pre_release_adjustment": True,
        "dimension_summary": [
            {
                "dimension_name": "问题提出",
                "mean": 5.0,
                "summary_comment": "优秀",
            },
            {
                "dimension_name": "方案新颖性",
                "mean": 5.0,
                "summary_comment": "优秀",
            },
            {
                "dimension_name": "创新表征",
                "mean": 5.0,
                "summary_comment": "优秀",
            },
            {
                "dimension_name": "创新表达",
                "mean": 5.0,
                "summary_comment": "优秀",
            },
        ],
        "primary_indicator_summary": [],
        "creativity": {"score": 2.0, "feedback": "旧分", "evidence": ""},
        "final_score": 2.0,
    }
    synced = sync_leader_display_payload(result)
    assert synced["creativity"]["score"] == 5.0
    assert synced["final_score"] == 5.0
