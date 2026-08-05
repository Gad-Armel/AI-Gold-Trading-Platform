from services.bot.scalping_config_validator import print_scalping_config_report
from services.bot.scalping_system_auditor import print_scalping_system_audit


def main() -> int:
    config = print_scalping_config_report()
    if not config["valid"]:
        print("Scalping audit stopped because the configuration is invalid.")
        return 1
    audit = print_scalping_system_audit()
    return 0 if audit["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
