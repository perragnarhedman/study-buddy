from app.models.schemas import Assignment
from app.services.planner import MAX_PLAN_ITEMS, generate_weekly_plan


def test_planner_splits_chunks_10_to_20() -> None:
    a = Assignment(
        id="x",
        title="Big assignment",
        dueDate="2026-01-20",
        courseName="Course",
        estimatedMinutes=60,
    )
    plan = generate_weekly_plan([a])
    mins = [i.estimatedMinutes for i in plan.items]
    titles = [i.title for i in plan.items]
    assert len(mins) == 4
    assert len(set(titles)) == 4
    assert all("Start Big assignment" in t for t in titles)
    assert all("(" in t and ")" in t for t in titles)
    assert all(m is not None and 10 <= m <= 20 for m in mins)


def test_planner_caps_at_15_items() -> None:
    many = [
        Assignment(
            id=f"a{i}",
            title=f"Task {i}",
            dueDate="2026-01-20",
            courseName="Course",
            estimatedMinutes=120,
        )
        for i in range(50)
    ]
    plan = generate_weekly_plan(many)
    assert len(plan.items) == MAX_PLAN_ITEMS


def test_planner_sorting_respects_due_date() -> None:
    a_late = Assignment(
        id="late",
        title="Later due",
        dueDate="2026-01-30",
        courseName="Course",
        estimatedMinutes=15,
    )
    a_early = Assignment(
        id="early",
        title="Earlier due",
        dueDate="2026-01-20",
        courseName="Course",
        estimatedMinutes=15,
    )
    a_none = Assignment(
        id="none",
        title="No due date",
        dueDate=None,
        courseName="Course",
        estimatedMinutes=15,
    )
    plan = generate_weekly_plan([a_late, a_none, a_early])
    assert plan.items[0].sourceAssignmentId == "early"
    assert plan.items[1].sourceAssignmentId == "late"
    assert plan.items[2].sourceAssignmentId == "none"


