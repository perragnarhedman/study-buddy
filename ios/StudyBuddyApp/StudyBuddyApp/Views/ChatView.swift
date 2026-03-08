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
    }

    private var messagesList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 10) {
                    ForEach(store.messages) { msg in
                        MessageRow(message: msg)
                            .id(msg.id)
                    }

                    if store.isAssistantTyping {
                        TypingIndicatorRow()
                            .id("typing-indicator")
                    }
                }
                .padding(.vertical, 12)
                .padding(.horizontal, 12)
            }
            .onChange(of: store.messages.count) {
                scrollToLatest(proxy: proxy, animated: true)
            }
            .onChange(of: store.messages.last?.id) {
                scrollToLatest(proxy: proxy, animated: true)
            }
            .onChange(of: store.messages.last?.text) {
                scrollToLatest(proxy: proxy, animated: true)
            }
            .onChange(of: store.isAssistantTyping) {
                scrollToLatest(proxy: proxy, animated: true)
            }
        }
    }

    private func scrollToLatest(proxy: ScrollViewProxy, animated: Bool) {
        if store.isAssistantTyping {
            if animated {
                withAnimation(.easeOut(duration: 0.2)) {
                    proxy.scrollTo("typing-indicator", anchor: .bottom)
                }
            } else {
                proxy.scrollTo("typing-indicator", anchor: .bottom)
            }
            return
        }
        guard let last = store.messages.last else { return }
        if animated {
            withAnimation(.easeOut(duration: 0.2)) {
                proxy.scrollTo(last.id, anchor: .bottom)
            }
        } else {
            proxy.scrollTo(last.id, anchor: .bottom)
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

    var isUser: Bool { message.role == .user }

    var body: some View {
        HStack {
            if isUser { Spacer(minLength: 40) }

            VStack(alignment: isUser ? .trailing : .leading, spacing: 4) {
                messageBubble(text: message.text, isUser: isUser)

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
            .multilineTextAlignment(.leading)
            .foregroundStyle(isUser ? .white : .primary)
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(isUser ? Color.accentColor : Color(.secondarySystemBackground))
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            .frame(maxWidth: 280, alignment: isUser ? .trailing : .leading)
    }
}

private struct TypingIndicatorRow: View {
    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                TypingIndicatorBubble()

                Text("Coach")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }

            Spacer(minLength: 40)
        }
    }
}

private struct TypingIndicatorBubble: View {
    var body: some View {
        TimelineView(.animation) { context in
            let phase = Int(context.date.timeIntervalSinceReferenceDate * 3) % 3

            HStack(spacing: 6) {
                ForEach(0..<3, id: \.self) { index in
                    Circle()
                        .fill(Color.secondary)
                        .frame(width: 8, height: 8)
                        .opacity(index == phase ? 1 : 0.3)
                        .scaleEffect(index == phase ? 1 : 0.85)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 12)
            .background(Color(.secondarySystemBackground))
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        }
        .frame(maxWidth: 280, alignment: .leading)
    }
}
