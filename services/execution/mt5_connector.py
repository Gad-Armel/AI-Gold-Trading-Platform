import MetaTrader5 as mt5


def connect_mt5():
    if not mt5.initialize():
        print("MT5 connection failed:", mt5.last_error())
        return False

    print("Connected to MT5")
    return True


def disconnect_mt5():
    mt5.shutdown()
    print("Disconnected from MT5")


def get_account_info():
    return mt5.account_info()


def get_open_positions(symbol=None):
    if symbol:
        return mt5.positions_get(symbol=symbol)
    return mt5.positions_get()