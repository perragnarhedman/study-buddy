import Foundation

/// Shared due-date display helper for Plan tab.
/// - Handles both `YYYY-MM-DD` and full ISO8601 timestamps.
/// - Returns weekday + date (no time), respecting locale.
enum DueDateDisplay {
    static func format(_ raw: String?) -> String? {
        guard let raw, !raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        guard let d = parse(raw) else { return nil }

        let f = DateFormatter()
        f.locale = .current
        f.timeZone = .current
        // Weekday + date, no time (example: Tue, Feb 5)
        f.setLocalizedDateFormatFromTemplate("EEE, MMM d")
        return f.string(from: d)
    }

    static func parse(_ raw: String) -> Date? {
        // 1) Common case: backend `weekStart`-like date.
        if let d = _ymdFormatter.date(from: raw) { return d }

        // 2) ISO8601 timestamps (with/without fractional seconds).
        if let d = _isoWithFractional.date(from: raw) { return d }
        if let d = _isoBasic.date(from: raw) { return d }

        return nil
    }

    private static let _ymdFormatter: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(secondsFromGMT: 0)
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    private static let _isoWithFractional: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    private static let _isoBasic: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()
}


