from tendura.config import Settings
from tendura.telegram.bot import build_application


def main() -> None:
    application = build_application(Settings.from_environ())
    application.run_polling()


if __name__ == "__main__":
    main()
