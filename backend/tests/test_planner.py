from app.models.schemas import Assignment
from app.services.planner import MAX_PLAN_ITEMS, generate_weekly_plan


def test_planner_creates_one_item_per_assignment_and_keeps_reasonable_minutes() -> None:
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
    assert len(mins) == 1
    assert len(set(titles)) == 1
    assert titles[0].startswith("Start Big assignment")
    assert mins[0] is not None and 10 <= mins[0] <= 180


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
