from app.services.classroom import _normalize_coursework


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


