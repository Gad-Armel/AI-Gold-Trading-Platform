from services.research.v63_self_learning import print_v63_self_learning_report, train_v63_self_learner


if __name__ == "__main__":
    report = train_v63_self_learner(force=True, promote=True)
    print_v63_self_learning_report(report)
