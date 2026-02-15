import SwiftUI

struct ChatView: View {
    @EnvironmentObject private var store: AppStore
    @State private var draft: String = ""

    var body: some View {
        VStack(spacing: 0) {
            if let msg = store.authErrorMessage {
                Text(msg)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
            }
            if let msg = store.chatInfoMessage {
                Text(msg)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
            }
            if let msg = store.chatErrorMessage {
                Text(msg)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
            }
            messagesList
            Divider()
            inputBar
        }
        .background(Color(.systemGroupedBackground))
        // Proactively load plan so /chat/send always has current_plan available.
        .task {
            guard !store.useStubData else { return }
            if store.weeklyPlan == nil || store.weeklyPlan?.items.isEmpty == true {
                await store.loadWeeklyPlan(preserveChatAction: true)
            }
        }
    }

    private var messagesList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 10) {
                    ForEach(store.messages) { msg in
                        MessageRow(
                            message: msg,
                            cards: store.assignmentCards(forAssistantMessageId: msg.id),
                            onMarkDone: { sid in
                                Task { await store.markDoneFromCard(sourceAssignmentId: sid) }
                            }
                        )
                            .id(msg.id)
                    }
                }
                .padding(.vertical, 12)
                .padding(.horizontal, 12)
            }
            .onChange(of: store.messages.count) {
                guard let last = store.messages.last else { return }
                withAnimation(.easeOut(duration: 0.2)) {
                    proxy.scrollTo(last.id, anchor: .bottom)
                }
            }
        }
    }

    private var inputBar: some View {
        HStack(spacing: 10) {
            TextField("What are you working on?", text: $draft, axis: .vertical)
                .lineLimit(1...4)
                .textInputAutocapitalization(.sentences)
                .autocorrectionDisabled(false)
                .padding(10)
                .background(.thinMaterial)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

            Button {
                let toSend = draft
                draft = ""
                Task { await store.sendUserMessage(toSend) }
            } label: {
                Text("Send")
                    .fontWeight(.semibold)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .background(Color.accentColor)
                    .foregroundStyle(.white)
                    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            }
            .disabled(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
        .padding(12)
        .background(Color(.systemBackground))
    }
}

private struct MessageRow: View {
    let message: ChatMessage
    let cards: [AssignmentCard]
    let onMarkDone: (String) -> Void

    var isUser: Bool { message.role == .user }

    var body: some View {
        HStack {
            if isUser { Spacer(minLength: 40) }

            VStack(alignment: isUser ? .trailing : .leading, spacing: 4) {
                if isUser {
                    messageBubble(text: message.text, isUser: true)
                } else {
                    assistantMessageWithCards(text: message.text, cards: cards)
                }

                Text(message.role == .assistant ? "Coach" : "You")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }

            if !isUser { Spacer(minLength: 40) }
        }
    }

    @ViewBuilder
    private func messageBubble(text: String, isUser: Bool) -> some View {
        Text(text)
            .font(.body)
            .foregroundStyle(isUser ? .white : .primary)
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(isUser ? Color.accentColor : Color(.secondarySystemBackground))
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    // Persist expand/collapse state per message row.
    @State private var expandedCardIds: Set<String> = []

    private struct AssistantSection: Identifiable {
        let id: String
        let text: String
        let subjectHint: String?
    }

    @ViewBuilder
    private func assistantMessageWithCards(text: String, cards: [AssignmentCard]) -> some View {
        // Split assistant message into sections (especially for numbered overview lists),
        // then render matching cards directly under each section.
        let sections = parseAssistantSections(text)
        var remaining = cards

        VStack(alignment: .leading, spacing: 10) {
            ForEach(sections) { sec in
                messageBubble(text: sec.text, isUser: false)

                if let hint = sec.subjectHint, !hint.isEmpty {
                    let matched = matchCards(subjectHint: hint, from: &remaining)
                    if !matched.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            ForEach(matched.prefix(3)) { c in
                                AssignmentCardRow(
                                    card: c,
                                    isExpanded: expandedCardIds.contains(c.id),
                                    onToggleExpanded: { toggleCard(id: c.id) },
                                    onMarkDone: onMarkDone
                                )
                            }
                        }
                        .padding(.top, 2)
                    }
                }
            }

            // Any leftover cards (no clear section match) go at the bottom.
            if !remaining.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(remaining.prefix(6)) { c in
                        AssignmentCardRow(
                            card: c,
                            isExpanded: expandedCardIds.contains(c.id),
                            onToggleExpanded: { toggleCard(id: c.id) },
                            onMarkDone: onMarkDone
                        )
                    }
                }
            }
        }
    }

    private func toggleCard(id: String) {
        if expandedCardIds.contains(id) {
            expandedCardIds.remove(id)
        } else {
            expandedCardIds.insert(id)
        }
    }

    private func parseAssistantSections(_ text: String) -> [AssistantSection] {
        let raw = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !raw.isEmpty else { return [] }

        // Split by blank lines into paragraphs.
        let paras = raw
            .components(separatedBy: "\n\n")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }

        // If it's a numbered list (common for overview), keep each numbered paragraph as its own section.
        // Otherwise, keep paragraphs as-is.
        var out: [AssistantSection] = []
        for (idx, p) in paras.enumerated() {
            let hint = extractSubjectHint(from: p)
            out.append(AssistantSection(id: "\(idx)", text: p, subjectHint: hint))
        }
        return out
    }

    private func extractSubjectHint(from paragraph: String) -> String? {
        // Match patterns like:
        // "1. Engelska: ...", "2. Historia: ...", "Historia: ...", "Engelska: ..."
        let pattern = #"^\s*(?:\d+\.\s*)?([^\:\n]{2,40})\s*:"#
        guard let re = try? NSRegularExpression(pattern: pattern, options: []) else { return nil }
        let range = NSRange(paragraph.startIndex..<paragraph.endIndex, in: paragraph)
        guard let m = re.firstMatch(in: paragraph, options: [], range: range) else { return nil }
        guard m.numberOfRanges >= 2, let r = Range(m.range(at: 1), in: paragraph) else { return nil }
        let s = paragraph[r].trimmingCharacters(in: .whitespacesAndNewlines)
        return s.isEmpty ? nil : s
    }

    private func matchCards(subjectHint: String, from cards: inout [AssignmentCard]) -> [AssignmentCard] {
        let hint = subjectHint.lowercased()
        // Lightweight Swedish↔English subject normalization for matching.
        let hintAlt: String? = {
            let m: [String: String] = [
                "historia": "history",
                "engelska": "english",
                "svenska": "swedish",
                "matte": "math",
                "matematik": "math",
                "biologi": "biology",
                "kemi": "chemistry",
                "fysik": "physics",
                "geografi": "geography",
            ]
            return m[hint]
        }()

        var matched: [AssignmentCard] = []
        var remaining: [AssignmentCard] = []
        for c in cards {
            let course = (c.courseName ?? "").lowercased()
            let title = c.title.lowercased()
            let okDirect = (!course.isEmpty && course.contains(hint)) || title.contains(hint)
            let okAlt = {
                guard let hintAlt else { return false }
                return (!course.isEmpty && course.contains(hintAlt)) || title.contains(hintAlt)
            }()
            if okDirect || okAlt {
                matched.append(c)
            } else {
                remaining.append(c)
            }
        }
        cards = remaining
        return matched
    }
}

private struct AssignmentCardRow: View {
    let card: AssignmentCard
    let isExpanded: Bool
    let onToggleExpanded: () -> Void
    let onMarkDone: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 12) {
                Circle()
                    .fill(dotColor)
                    .frame(width: 10, height: 10)
                    .padding(.top, 6)

                VStack(alignment: .leading, spacing: 4) {
                    if let course = card.courseName, !course.isEmpty {
                        Text(course)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Text(card.title)
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .foregroundStyle(.primary)
                        .lineLimit(isExpanded ? 3 : 1)

                    HStack(spacing: 10) {
                        if let mins = card.estimatedMinutes {
                            Label("\(mins) min", systemImage: "clock")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        if let dueText = DueDateDisplay.format(card.dueDate) {
                            Label(dueText, systemImage: "calendar")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }

                Spacer(minLength: 0)

                VStack(alignment: .trailing, spacing: 8) {
                    StatusPill(status: card.status)
                    if card.status != .done {
                        Button("Done") {
                            let sid = (card.sourceAssignmentId ?? card.id)
                            if !sid.isEmpty {
                                onMarkDone(sid)
                            }
                        }
                        .font(.caption.weight(.semibold))
                        .buttonStyle(.bordered)
                    }
                }
            }
            .contentShape(Rectangle())
            .onTapGesture { onToggleExpanded() }

            if isExpanded {
                if let urlStr = card.url, let u = URL(string: urlStr) {
                    Link("Open link", destination: u)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                if let attachments = card.attachments, !attachments.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(attachments.prefix(4), id: \.url) { a in
                            if let u = URL(string: a.url) {
                                Link(a.title, destination: u)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            } else {
                Text("Tap to expand")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(12)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private var dotColor: Color {
        switch card.status {
        case .todo: return .orange
        case .doing: return .blue
        case .done: return .green
        }
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


