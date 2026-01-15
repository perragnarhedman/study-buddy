import SwiftUI

struct PlanView: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                bestNextActionCard

                VStack(alignment: .leading, spacing: 10) {
                    Text("This Week")
                        .font(.headline)

                    if let plan = store.weeklyPlan {
                        ForEach(plan.items) { item in
                            PlanRow(item: item)
                        }
                    } else {
                        Text("Loading plan…")
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .padding(16)
        }
        .background(Color(.systemGroupedBackground))
        .refreshable {
            await store.loadWeeklyPlan()
        }
    }

    private var bestNextActionCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Best Next Action")
                .font(.headline)

            if let action = store.bestNextAction {
                Text(action.title)
                    .font(.body)
                    .fontWeight(.semibold)

                HStack(spacing: 10) {
                    if let mins = action.estimatedMinutes {
                        Label("\(mins) min", systemImage: "timer")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    if let due = action.dueDate, !due.isEmpty {
                        Label("Due \(due)", systemImage: "calendar")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                }

                Button {
                    // MVP: no status mutation yet. This is a “do now” affordance.
                } label: {
                    Text("Start now")
                        .fontWeight(.semibold)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
                }
                .buttonStyle(.borderedProminent)
            } else {
                Text("No plan yet. Pull to refresh.")
                    .foregroundStyle(.secondary)
            }
        }
        .padding(14)
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .shadow(color: Color.black.opacity(0.05), radius: 10, y: 4)
    }
}

private struct PlanRow: View {
    let item: PlanItem

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Circle()
                .fill(dotColor)
                .frame(width: 10, height: 10)
                .padding(.top, 6)

            VStack(alignment: .leading, spacing: 4) {
                Text(item.title)
                    .font(.body)
                    .fontWeight(.medium)

                HStack(spacing: 10) {
                    if let mins = item.estimatedMinutes {
                        Text("\(mins) min")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    if let due = item.dueDate, !due.isEmpty {
                        Text("Due \(due)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            Spacer()
        }
        .padding(12)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private var dotColor: Color {
        switch item.status {
        case .todo: return .orange
        case .doing: return .blue
        case .done: return .green
        }
    }
}


