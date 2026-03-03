from app.services.classroom import _normalize_announcements, _normalize_coursework, _normalize_coursework_materials


def test_classroom_materials_are_embedded_in_description_and_url() -> None:
    coursework = [
        {
            "id": "cw1",
            "title": "Read Chapter 3",
            "description": "Read the chapter and answer questions.",
            "alternateLink": "https://classroom.google.com/c/abc",
            "materials": [
                {
                    "driveFile": {
                        "driveFile": {
                            "title": "Chapter 3 PDF",
                            "alternateLink": "https://drive.google.com/file/d/123/view",
                        }
                    }
                },
                {"link": {"title": "Extra resource", "url": "https://example.com/resource"}},
            ],
        }
    ]

    out = _normalize_coursework(coursework, "English")
    assert len(out) == 1
    a = out[0]
    assert a.url == "https://drive.google.com/file/d/123/view"
    assert a.description is not None
    assert "Attachments:" in a.description
    assert "Chapter 3 PDF" in a.description
    assert "https://drive.google.com/file/d/123/view" in a.description
    assert "Extra resource" in a.description
    assert "https://example.com/resource" in a.description


def test_coursework_materials_are_normalized_with_attachments_and_primary_url() -> None:
    materials = [
        {
            "id": "m1",
            "title": "Syllabus",
            "description": "Read before class.",
            "alternateLink": "https://classroom.google.com/c/abc/m/m1",
            "updateTime": "2026-03-01T10:00:00Z",
            "topicId": "t1",
            "materials": [{"link": {"title": "PDF", "url": "https://example.com/syllabus.pdf"}}],
        }
    ]

    out = _normalize_coursework_materials(materials, "Biology")
    assert len(out) == 1
    m = out[0]
    assert m.id == "m1"
    assert m.title == "Syllabus"
    assert m.courseName == "Biology"
    assert m.description == "Read before class."
    assert m.topicId == "t1"
    assert m.updatedAt == "2026-03-01T10:00:00Z"
    assert m.url == "https://example.com/syllabus.pdf"
    assert m.attachments is not None
    assert m.attachments[0].title == "PDF"
    assert m.attachments[0].url == "https://example.com/syllabus.pdf"


def test_announcements_are_normalized_with_attachments_and_primary_url() -> None:
    announcements = [
        {
            "id": "a1",
            "text": "Quiz moved to Friday.",
            "alternateLink": "https://classroom.google.com/c/abc/a/a1",
            "updateTime": "2026-03-02T12:00:00Z",
            "materials": [{"link": {"title": "Details", "url": "https://example.com/details"}}],
        }
    ]

    out = _normalize_announcements(announcements, "Math")
    assert len(out) == 1
    a = out[0]
    assert a.id == "a1"
    assert a.courseName == "Math"
    assert a.text == "Quiz moved to Friday."
    assert a.updatedAt == "2026-03-02T12:00:00Z"
    assert a.url == "https://example.com/details"
    assert a.attachments is not None
    assert a.attachments[0].title == "Details"
    assert a.attachments[0].url == "https://example.com/details"

