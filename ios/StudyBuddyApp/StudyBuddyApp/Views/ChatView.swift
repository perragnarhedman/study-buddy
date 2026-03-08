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
            if store.isIntroMode {
                Text("Sign in from Settings to connect Google Classroom.")
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
            TextField(store.isIntroMode ? "Ask what Study Buddy can do" : "What are you working on?", text: $draft, axis: .vertical)
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
    private let assistantBubbleColor = Color(red: 0.20, green: 0.78, blue: 0.35)

    var body: some View {
        HStack(alignment: .bottom, spacing: 8) {
            if isUser {
                Spacer(minLength: 40)
                messageBubble(text: message.text, isUser: true)
            } else {
                assistantAvatar
                messageBubble(text: message.text, isUser: false)
                Spacer(minLength: 40)
            }
        }
    }

    @ViewBuilder
    private func messageBubble(text: String, isUser: Bool) -> some View {
        Text(formattedMessageText(text))
            .font(.body)
            .multilineTextAlignment(.leading)
            .foregroundStyle(.white)
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .fill(isUser ? Color.accentColor : assistantBubbleColor)
                    .shadow(color: (isUser ? Color.accentColor : assistantBubbleColor).opacity(0.18), radius: 8, y: 2)
            )
            .frame(maxWidth: 300, alignment: isUser ? .trailing : .leading)
    }

    private func formattedMessageText(_ text: String) -> AttributedString {
        let options = AttributedString.MarkdownParsingOptions(
            interpretedSyntax: .inlineOnlyPreservingWhitespace
        )
        if let formatted = try? AttributedString(markdown: text, options: options) {
            return formatted
        }
        return AttributedString(text.replacingOccurrences(of: "**", with: ""))
    }

    private var assistantAvatar: some View {
        ZStack {
            Circle()
                .fill(assistantBubbleColor.opacity(0.18))
            Image(systemName: "sparkles")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(assistantBubbleColor)
        }
        .frame(width: 28, height: 28)
    }
}

private struct TypingIndicatorRow: View {
    private let assistantBubbleColor = Color(red: 0.20, green: 0.78, blue: 0.35)

    var body: some View {
        HStack(alignment: .bottom, spacing: 8) {
            ZStack {
                Circle()
                    .fill(assistantBubbleColor.opacity(0.18))
                Image(systemName: "sparkles")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(assistantBubbleColor)
            }
            .frame(width: 28, height: 28)
            TypingIndicatorBubble()
            Spacer(minLength: 40)
        }
    }
}

private struct TypingIndicatorBubble: View {
    private let assistantBubbleColor = Color(red: 0.20, green: 0.78, blue: 0.35)

    var body: some View {
        TimelineView(.animation) { context in
            let phase = Int(context.date.timeIntervalSinceReferenceDate * 3) % 3

            HStack(spacing: 6) {
                ForEach(0..<3, id: \.self) { index in
                    Circle()
                        .fill(Color.white)
                        .frame(width: 8, height: 8)
                        .opacity(index == phase ? 1 : 0.45)
                        .scaleEffect(index == phase ? 1 : 0.85)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 12)
            .background(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .fill(assistantBubbleColor)
                    .shadow(color: assistantBubbleColor.opacity(0.18), radius: 8, y: 2)
            )
        }
        .frame(maxWidth: 300, alignment: .leading)
    }
}
