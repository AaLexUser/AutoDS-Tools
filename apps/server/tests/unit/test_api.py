from autods_web.api import create_app


def test_create_app() -> None:
    app = create_app()

    assert app.title == "AutoDS API"
