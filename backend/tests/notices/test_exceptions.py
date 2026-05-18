from app.notices.exceptions import (
    DraftNotFoundError, NoticeError, NoticeInvalidStateError,
    NoticeNotFoundError, NoticeParseError, NoticeUnsupportedTypeError,
)


def test_notice_not_found_has_code_and_status():
    e = NoticeNotFoundError("nope")
    assert e.code == "NOTICE_NOT_FOUND"
    assert e.status_code == 404


def test_notice_unsupported_type_carries_filename_mime():
    e = NoticeUnsupportedTypeError(filename="x.docx", mime="application/msword")
    assert e.code == "NOTICE_UNSUPPORTED_TYPE"
    assert e.status_code == 415
    assert "x.docx" in e.message


def test_notice_parse_error_400():
    e = NoticeParseError("could not extract BIN")
    assert e.code == "NOTICE_PARSE_ERROR"
    assert e.status_code == 400


def test_notice_invalid_state_409():
    e = NoticeInvalidStateError("cannot draft from status=pending")
    assert e.code == "NOTICE_INVALID_STATE"
    assert e.status_code == 409


def test_draft_not_found_404():
    e = DraftNotFoundError("no draft yet")
    assert e.code == "DRAFT_NOT_FOUND"
    assert e.status_code == 404


def test_all_inherit_from_notice_error():
    for cls in (NoticeNotFoundError, NoticeUnsupportedTypeError,
                NoticeParseError, NoticeInvalidStateError, DraftNotFoundError):
        assert issubclass(cls, NoticeError)
