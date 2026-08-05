from config import scalping_settings
from config import settings as core_settings
from services.news.official_data_updater import update_official_provider_cache
from services.risk.automatic_economic_calendar import sync_auto_economic_calendar


if __name__ == "__main__":
    calendar = sync_auto_economic_calendar(force=True)
    result = update_official_provider_cache()

    print("=" * 70)
    print("UNIFIED NEWS AND ECONOMIC-CALENDAR UPDATE")
    print("=" * 70)
    print(
        f"Calendar: {'HEALTHY' if calendar.get('success') else 'FAILED'} | "
        f"provider={calendar.get('provider')} | "
        f"events={calendar.get('total_events', 0)} | "
        f"{calendar.get('message', '')}"
    )
    for name, record in result["providers"].items():
        print(
            f"{name}: {'HEALTHY' if record['healthy'] else 'UNAVAILABLE'} | "
            f"{record['capability']} | {record['message']}"
        )
    print(f"Calendar file: {getattr(core_settings, 'NEWS_EVENTS_FILE', 'data/economic_events.json')}")
    print(f"Provider cache: {scalping_settings.SCALPING_UNIFIED_PROVIDER_CACHE_FILE}")
    print("Unverified conservative dates hard-block trading: NO")
    print("Provider health is directional news: NO")
    print("=" * 70)
