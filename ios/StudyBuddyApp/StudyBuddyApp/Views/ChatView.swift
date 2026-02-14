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
                Text(message.text)
                    .font(.body)
                    .foregroundStyle(isUser ? .white : .primary)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 10)
                    .background(isUser ? Color.accentColor : Color(.secondarySystemBackground))
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))

                if !isUser, !cards.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(cards.prefix(6)) { c in
                            AssignmentCardRow(card: c, onMarkDone: onMarkDone)
                        }
                    }
                    .padding(.top, 4)
                }

                Text(message.role == .assistant ? "Coach" : "You")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }

            if !isUser { Spacer(minLength: 40) }
        }
    }
}

private struct AssignmentCardRow: View {
    let card: AssignmentCard
    let onMarkDone: (String) -> Void

    var body: some View {
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
                    .lineLimit(2)

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

                if let attachments = card.attachments, !attachments.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(attachments.prefix(2), id: \.url) { a in
                            if let u = URL(string: a.url) {
                                Link(a.title, destination: u)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }

            Spacer(minLength: 0)

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


