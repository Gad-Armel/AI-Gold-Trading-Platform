from services.research.v6_walk_forward import build_v6_walk_forward_report, print_v6_walk_forward_report

if __name__ == "__main__":
    report=build_v6_walk_forward_report(write_approval=True)
    print_v6_walk_forward_report(report)
    raise SystemExit(0 if report["approved"] else 2)
