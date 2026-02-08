import SwiftUI

struct PlanView: View {
    @EnvironmentObject private var store: AppStore
    @Environment(\.openURL) private var openURL

    @State private var showAllThisWeek = false
    @State private var showAllNextWeek = false
    @State private var showAllLater = false

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                if let auth = store.authErrorMessage {
                    Text(auth)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else if let err = store.planErrorMessage {
                    Text(err)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else if let plan = store.weeklyPlan {
                    let buckets = bucketedItems(plan: plan)
                    let bestNext = store.bestNextAction

                    if buckets.thisWeek.isEmpty && buckets.nextWeek.isEmpty && buckets.later.isEmpty {
                        Text("No plan items yet. Pull to refresh.")
                            .foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    } else {
                        if !buckets.thisWeek.isEmpty {
                            PlanSection(
                                title: "This Week",
                                items: visibleItems(buckets.thisWeek, showAll: showAllThisWeek, defaultCount: 3),
                                totalCount: buckets.thisWeek.count,
                                showAll: $showAllThisWeek
                            ) { item in
                                PlanRow(
                                    item: item,
                                    courseName: store.assignmentCourseName(forSourceAssignmentId: item.sourceAssignmentId),
                                    isBestNext: isBestNext(item: item, bestNext: bestNext),
                                    onStart: { start(item: item) }
                                )
                            }
                        }

                        if !buckets.nextWeek.isEmpty {
                            PlanSection(
                                title: "Next Week",
                                items: visibleItems(buckets.nextWeek, showAll: showAllNextWeek, defaultCount: 2),
                                totalCount: buckets.nextWeek.count,
                                showAll: $showAllNextWeek
                            ) { item in
                                PlanRow(
                                    item: item,
                                    courseName: store.assignmentCourseName(forSourceAssignmentId: item.sourceAssignmentId),
                                    isBestNext: isBestNext(item: item, bestNext: bestNext),
                                    onStart: { start(item: item) }
                                )
                            }
                        }

                        if !buckets.later.isEmpty {
                            PlanSection(
                                title: "Later",
                                items: visibleItems(buckets.later, showAll: showAllLater, defaultCount: 2),
                                totalCount: buckets.later.count,
                                showAll: $showAllLater
                            ) { item in
                                PlanRow(
                                    item: item,
                                    courseName: store.assignmentCourseName(forSourceAssignmentId: item.sourceAssignmentId),
                                    isBestNext: isBestNext(item: item, bestNext: bestNext),
                                    onStart: { start(item: item) }
                                )
                            }
                        }
                    }
                } else {
                    Text("Loading plan…")
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .padding(.horizontal, 16)
            .padding(.top, 12)
            .padding(.bottom, 24)
        }
        .background(Color(.systemGroupedBackground))
        .refreshable {
            await store.loadWeeklyPlan()
        }
    }

    private func start(item: PlanItem) {
        // Compact “Starta” affordance: open the primary assignment URL if available.
        if let url = store.assignmentURL(forSourceAssignmentId: item.sourceAssignmentId) {
            openURL(url)
        }
    }

    private func isBestNext(item: PlanItem, bestNext: PlanItem?) -> Bool {
        guard let bestNext else { return false }
        if item.id == bestNext.id { return true }
        if let a = item.sourceAssignmentId, let b = bestNext.sourceAssignmentId, !a.isEmpty, a == b { return true }
        return false
    }

    private struct Buckets {
        let thisWeek: [PlanItem]
        let nextWeek: [PlanItem]
        let later: [PlanItem]
    }

    private func bucketedItems(plan: WeeklyPlan) -> Buckets {
        let weekStart = DueDateDisplay.parse(plan.weekStart) ?? Date()
        let cal = Calendar.current
        let startOfWeek = cal.startOfDay(for: weekStart)
        let startNextWeek = cal.date(byAdding: .day, value: 7, to: startOfWeek) ?? startOfWeek
        let startWeekAfterNext = cal.date(byAdding: .day, value: 14, to: startOfWeek) ?? startNextWeek

        func sortKey(_ item: PlanItem) -> (Date, String) {
            let due = DueDateDisplay.parse(item.dueDate ?? "") ?? Date.distantFuture
            return (due, item.title.lowercased())
        }

        var thisWeek: [PlanItem] = []
        var nextWeek: [PlanItem] = []
        var later: [PlanItem] = []

        for it in plan.items {
            guard let dueRaw = it.dueDate, let due = DueDateDisplay.parse(dueRaw) else {
                later.append(it)
                continue
            }
            if due < startNextWeek {
                thisWeek.append(it)
            } else if due < startWeekAfterNext {
                nextWeek.append(it)
            } else {
                later.append(it)
            }
        }

        thisWeek.sort(by: { sortKey($0) < sortKey($1) })
        nextWeek.sort(by: { sortKey($0) < sortKey($1) })
        later.sort(by: { sortKey($0) < sortKey($1) })

        return Buckets(thisWeek: thisWeek, nextWeek: nextWeek, later: later)
    }

    private func visibleItems(_ items: [PlanItem], showAll: Bool, defaultCount: Int) -> [PlanItem] {
        guard !showAll else { return items }
        return Array(items.prefix(max(0, defaultCount)))
    }
}

private struct PlanSection<RowContent: View>: View {
    let title: String
    let items: [PlanItem]
    let totalCount: Int
    @Binding var showAll: Bool
    let row: (PlanItem) -> RowContent

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(title)
                    .font(.title3.weight(.bold))
                Spacer()
                if totalCount > items.count {
                    Button("Visa alla (\(totalCount))") { showAll = true }
                        .font(.subheadline.weight(.semibold))
                } else if showAll && totalCount > 0 {
                    Button("Visa mindre") { showAll = false }
                        .font(.subheadline.weight(.semibold))
                }
            }

            VStack(spacing: 0) {
                ForEach(items) { it in
                    row(it)
                    if it.id != items.last?.id {
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

private struct PlanRow: View {
    let item: PlanItem
    let courseName: String?
    let isBestNext: Bool
    let onStart: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            SubjectBadge(subjectName: courseName ?? "Other")

            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 8) {
                    if let courseName, !courseName.isEmpty {
                        Text(courseName)
                            .font(.headline)
                            .foregroundStyle(.primary)
                            .lineLimit(1)
                    }
                    if isBestNext {
                        BestNextBadge()
                    }
                    Spacer(minLength: 0)
                }

                Text(item.title)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)

                HStack(spacing: 10) {
                    if let mins = item.estimatedMinutes {
                        Label("\(mins) min", systemImage: "clock")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    if let dueText = DueDateDisplay.format(item.dueDate) {
                        Label(dueText, systemImage: "calendar")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                if let attachments = item.attachments, !attachments.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(attachments.prefix(3), id: \.url) { a in
                            if let u = URL(string: a.url) {
                                Link(a.title, destination: u)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                    .padding(.top, 2)
                }
            }

            Spacer(minLength: 0)

            VStack(alignment: .trailing, spacing: 8) {
                StatusPill(status: item.status)
                if isBestNext {
                    Button(action: onStart) {
                        HStack(spacing: 6) {
                            Image(systemName: "play.fill")
                                .font(.caption.weight(.semibold))
                            Text("Starta")
                                .font(.subheadline.weight(.semibold))
                        }
                        .padding(.vertical, 8)
                        .padding(.horizontal, 12)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(Color(.systemGreen))
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                }
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(isBestNext ? Color(.systemGreen).opacity(0.10) : Color.clear)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(isBestNext ? Color(.systemGreen).opacity(0.35) : Color.clear, lineWidth: 1)
        )
    }
}

private struct BestNextBadge: View {
    var body: some View {
        Text("Best next")
            .font(.caption.weight(.semibold))
            .padding(.vertical, 4)
            .padding(.horizontal, 8)
            .background(
                Capsule().fill(Color(.systemGreen).opacity(0.16))
            )
            .foregroundStyle(Color(.systemGreen))
            .overlay(
                Capsule().stroke(Color(.systemGreen).opacity(0.25), lineWidth: 1)
            )
    }
}

private struct SubjectBadge: View {
    let subjectName: String

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(style.color.opacity(0.15))
            Image(systemName: style.icon)
                .font(.headline)
                .foregroundStyle(style.color)
        }
        .frame(width: 40, height: 40)
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(style.color.opacity(0.25), lineWidth: 1)
        )
        .accessibilityLabel(subjectName)
    }

    private var style: SubjectStyle {
        SubjectStyle.forSubjectName(subjectName)
    }
}

private struct SubjectStyle {
    let color: Color
    let icon: String

    static func forSubjectName(_ name: String) -> SubjectStyle {
        let n = name.trimmingCharacters(in: .whitespacesAndNewlines)
        let lower = n.lowercased()

        let icon: String
        if lower.contains("math") || lower.contains("matte") { icon = "function" }
        else if lower.contains("svenska") || lower.contains("swedish") { icon = "book" }
        else if lower.contains("english") { icon = "textformat" }
        else if lower.contains("history") || lower.contains("historia") { icon = "globe.europe.africa" }
        else if lower.contains("science") || lower.contains("kemi") || lower.contains("fysik") { icon = "atom" }
        else { icon = "bookmark" }

        let palette: [Color] = [.blue, .red, .green, .purple, .orange, .teal, .indigo]
        let idx = stableIndex(n, modulo: palette.count)
        return SubjectStyle(color: palette[idx], icon: icon)
    }

    private static func stableIndex(_ s: String, modulo: Int) -> Int {
        guard modulo > 0 else { return 0 }
        var h: Int = 0
        for u in s.unicodeScalars {
            h = (h &* 31) &+ Int(u.value)
        }
        h = abs(h)
        return h % modulo
    }
}

private struct StatusPill: View {
    let status: PlanItem.Status

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
                .font(.caption.weight(.semibold))
            Text(label)
                .font(.caption.weight(.semibold))
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 10)
        .background(
            Capsule().fill(tint.opacity(0.15))
        )
        .foregroundStyle(tint)
        .overlay(
            Capsule().stroke(tint.opacity(0.25), lineWidth: 1)
        )
        .accessibilityLabel(label)
    }

    private var icon: String {
        switch status {
        case .todo: return "circle"
        case .doing: return "clock"
        case .done: return "checkmark.circle.fill"
        }
    }

    private var label: String {
        switch status {
        case .todo: return "Todo"
        case .doing: return "Doing"
        case .done: return "Done"
        }
    }

    private var tint: Color {
        switch status {
        case .todo: return .gray
        case .doing: return .orange
        case .done: return .green
        }
    }
}


