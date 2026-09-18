def main() -> None:
    print(
        "Run `uv run uvicorn --app-dir src infrastructure.entrypoint.fastapi_app:app --reload --host 127.0.0.1 --port 8002` to start the API."
    )


if __name__ == "__main__":
    main()
