# be-7hw — Plan tab readability & polish

## Alternative 2 (reference)

- **Goal**: improve Plan tab information hierarchy with compact best-next presentation, week sections, and clearer status affordances.
- **Screenshot**: add the image file at `designs/be-7hw/alternative2_plan_tab.png` and it will render below.

![Alternative 2 plan tab](alternative2_plan_tab.png)

## Notes

- This design includes a compact **Best next** card. The current epic `be-7hw` requires: *remove the large Best Next block* and *highlight best next inline*.
  - Treat this card as a *visual reference* for typography/spacing/badges; implementation should still satisfy the ticket requirements (inline highlight).

## Sample SwiftUI (prototype)

The following prototype was provided to illustrate the intended component structure (subject badge, status pill, grouped section cards, compact CTA):

Below are sample code that can be used for reference.

import SwiftUI

// MARK: - Models

enum AssignmentStatus: String, CaseIterable, Identifiable {
    case notStarted = "Inte startad"
    case inProgress = "Pågår"
    case done = "Klart"

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .notStarted: return "circle"
        case .inProgress: return "clock"
        case .done: return "checkmark.circle.fill"
        }
    }

    // Use your own palette / design tokens here.
    var tint: Color {
        switch self {
        case .notStarted: return .gray
        case .inProgress: return .orange
        case .done: return .green
        }
    }
}

struct Subject: Identifiable, Hashable {
    let id = UUID()
    let name: String
    let color: Color
    let icon: String
}

struct Assignment: Identifiable {
    let id = UUID()
    let subject: Subject
    let title: String
    let due: String       // display-only: "Ons 26 feb"
    let etaMinutes: Int?  // optional: 90
    var status: AssignmentStatus
}

// MARK: - Sample Data

enum SampleData {
    static let math = Subject(name: "Math", color: .blue, icon: "function")
    static let swedish = Subject(name: "Svenska", color: .red, icon: "book")
    static let history = Subject(name: "Historia", color: .green, icon: "globe.europe.africa")

    static let bestNext = Assignment(
        subject: history,
        title: "Historieläxa om Andra världskriget",
        due: "Ons 26 feb",
        etaMinutes: 90,
        status: .notStarted
    )

    static let thisWeek: [Assignment] = [
        Assignment(subject: math, title: "Tal och procent", due: "Ons 26 feb", etaMinutes: 30, status: .notStarted),
        Assignment(subject: swedish, title: "Läsförståelse – kapitel 4", due: "Tors 27 feb", etaMinutes: 25, status: .inProgress),
        Assignment(subject: history, title: "Källkritik: uppgift 2", due: "Fre 28 feb", etaMinutes: 20, status: .done),
        Assignment(subject: math, title: "Geometri – träningsblad", due: "Fre 28 feb", etaMinutes: 35, status: .notStarted),
        Assignment(subject: swedish, title: "Skriv en kort berättelse", due: "Sön 1 mars", etaMinutes: 40, status: .notStarted)
    ]

    static let nextWeek: [Assignment] = [
        Assignment(subject: math, title: "Algebra – ekvationer", due: "Ons 4 mars", etaMinutes: 35, status: .notStarted),
        Assignment(subject: swedish, title: "Ordklasser – övningar", due: "Tors 5 mars", etaMinutes: 25, status: .notStarted)
    ]
}

// MARK: - View

struct PlanOptionBAlternative2View: View {
    @State private var showAllThisWeek = false
    @State private var showAllNextWeek = false

    @State private var bestNext = SampleData.bestNext
    @State private var thisWeek = SampleData.thisWeek
    @State private var nextWeek = SampleData.nextWeek

    private var thisWeekVisible: [Assignment] {
        showAllThisWeek ? thisWeek : Array(thisWeek.prefix(3))
    }

    private var nextWeekVisible: [Assignment] {
        showAllNextWeek ? nextWeek : Array(nextWeek.prefix(2))
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    BestNextCompactCard(
                        assignment: bestNext,
                        onStart: { start(assignment: bestNext) }
                    )

                    WeekSection(
                        title: "This Week",
                        items: thisWeekVisible,
                        totalCount: thisWeek.count,
                        showAll: $showAllThisWeek,
                        showAllLabel: "Visa alla",
                        onTap: { _ in },
                        onStatusTap: { assignment in
                            cycleStatus(for: assignment.id, in: &thisWeek)
                        }
                    )

                    WeekSection(
                        title: "Next Week",
                        items: nextWeekVisible,
                        totalCount: nextWeek.count,
                        showAll: $showAllNextWeek,
                        showAllLabel: "Visa alla",
                        onTap: { _ in },
                        onStatusTap: { assignment in
                            cycleStatus(for: assignment.id, in: &nextWeek)
                        }
                    )
                }
                .padding(.horizontal, 16)
                .padding(.top, 12)
                .padding(.bottom, 24)
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Plan")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        // settings
                    } label: {
                        Image(systemName: "gearshape")
                    }
                }
            }
        }
    }

    // MARK: - Actions

    private func start(assignment: Assignment) {
        // Your "start progress" action (navigate to detail, open chat, start timer, etc)
        // Here we just set status to inProgress as a demo.
        bestNext.status = .inProgress
    }

    private func cycleStatus(for id: UUID, in list: inout [Assignment]) {
        guard let idx = list.firstIndex(where: { $0.id == id }) else { return }
        switch list[idx].status {
        case .notStarted: list[idx].status = .inProgress
        case .inProgress: list[idx].status = .done
        case .done: list[idx].status = .notStarted
        }
    }
}

// MARK: - Components

struct BestNextCompactCard: View {
    let assignment: Assignment
    let onStart: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Bästa nästa uppgift")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.secondary)

            HStack(alignment: .top, spacing: 12) {
                SubjectBadge(subject: assignment.subject)

                VStack(alignment: .leading, spacing: 6) {
                    Text(assignment.title)
                        .font(.headline)
                        .foregroundStyle(.primary)
                        .lineLimit(2)

                    HStack(spacing: 8) {
                        if let eta = assignment.etaMinutes {
                            Label("\(eta) min", systemImage: "clock")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Label(assignment.due, systemImage: "calendar")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    StatusPill(status: assignment.status)
                }

                Spacer(minLength: 0)

                // Compact "Start progress" representation:
                // a pill-like button instead of a huge primary CTA.
                Button(action: onStart) {
                    HStack(spacing: 6) {
                        Image(systemName: "play.fill")
                            .font(.caption.weight(.semibold))
                        Text("Starta")
                            .font(.subheadline.weight(.semibold))
                    }
                    .padding(.vertical, 10)
                    .padding(.horizontal, 14)
                }
                .buttonStyle(.borderedProminent)
                .tint(Color(.systemGreen))
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                .accessibilityLabel("Starta bästa nästa uppgift")
            }
        }
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(Color(.secondarySystemGroupedBackground))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color.black.opacity(0.05), lineWidth: 1)
        )
    }
}

struct WeekSection: View {
    let title: String
    let items: [Assignment]
    let totalCount: Int
    @Binding var showAll: Bool
    let showAllLabel: String

    let onTap: (Assignment) -> Void
    let onStatusTap: (Assignment) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(title)
                    .font(.title3.weight(.bold))
                Spacer()
                if totalCount > items.count {
                    Button("\(showAllLabel) (\(totalCount))") { showAll = true }
                        .font(.subheadline.weight(.semibold))
                } else if showAll && totalCount > 0 {
                    Button("Visa mindre") { showAll = false }
                        .font(.subheadline.weight(.semibold))
                }
            }

            VStack(spacing: 0) {
                ForEach(items) { a in
                    AssignmentRow(
                        assignment: a,
                        onTap: { onTap(a) },
                        onStatusTap: { onStatusTap(a) }
                    )
                    if a.id != items.last?.id {
                        Divider().padding(.leading, 56)
                    }
                }
            }
            .background(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .fill(Color(.secondarySystemGroupedBackground))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .stroke(Color.black.opacity(0.05), lineWidth: 1)
            )
        }
    }
}

struct AssignmentRow: View {
    let assignment: Assignment
    let onTap: () -> Void
    let onStatusTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 12) {
                SubjectBadge(subject: assignment.subject)

                VStack(alignment: .leading, spacing: 4) {
                    Text(assignment.subject.name)
                        .font(.headline)
                        .foregroundStyle(.primary)
                        .lineLimit(1)

                    Text(assignment.title)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }

                Spacer()

                VStack(alignment: .trailing, spacing: 6) {
                    Text(assignment.due)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)

                    Button(action: onStatusTap) {
                        StatusPill(status: assignment.status)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Ändra status: \(assignment.status.rawValue)")
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

struct SubjectBadge: View {
    let subject: Subject

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(subject.color.opacity(0.15))
            Image(systemName: subject.icon)
                .font(.headline)
                .foregroundStyle(subject.color)
        }
        .frame(width: 40, height: 40)
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(subject.color.opacity(0.25), lineWidth: 1)
        )
    }
}

struct StatusPill: View {
    let status: AssignmentStatus

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: status.icon)
                .font(.caption.weight(.semibold))
            Text(status.rawValue)
                .font(.caption.weight(.semibold))
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 10)
        .background(
            Capsule().fill(status.tint.opacity(0.15))
        )
        .foregroundStyle(status.tint)
        .overlay(
            Capsule().stroke(status.tint.opacity(0.25), lineWidth: 1)
        )
    }
}

// MARK: - Preview

#Preview {
    PlanOptionBAlternative2View()
}

