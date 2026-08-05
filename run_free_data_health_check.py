from services.news.free_macro_context import build_free_macro_health

if __name__ == "__main__":
    report=build_free_macro_health()
    print("\nFREE / OFFICIAL CONTEXT PROVIDER HEALTH")
    print("Context only — MT5 remains authoritative for prices and orders.")
    for item in report["providers"]:
        print(f"{item['provider']}: {'PASS' if item['success'] else 'SKIP/FAIL'} — {item['message']}")
