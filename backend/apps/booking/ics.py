"""Minimal RFC 5545 calendar file. Hand-written to avoid a dependency for ~40 lines."""

from datetime import UTC, datetime


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    # Lines longer than 75 octets are folded with CRLF + space.
    out, current = [], b""
    for ch in line:
        encoded = ch.encode()
        if len(current) + len(encoded) > 75:
            out.append(current.decode())
            current = b" " + encoded
        else:
            current += encoded
    out.append(current.decode())
    return "\r\n".join(out)


def _ts(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def build_ics(*, uid: str, events: list[tuple[datetime, datetime]], summary: str, description: str, location: str) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//learnspace//booking//ES", "CALSCALE:GREGORIAN", "METHOD:PUBLISH"]
    stamp = _ts(datetime.now(UTC))
    for i, (start, end) in enumerate(events):
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}-{i}@learnspace",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{_ts(start)}",
            f"DTEND:{_ts(end)}",
            f"SUMMARY:{_escape(summary)}",
            f"DESCRIPTION:{_escape(description)}",
            f"LOCATION:{_escape(location)}",
            "BEGIN:VALARM", "TRIGGER:-PT2H", "ACTION:DISPLAY", f"DESCRIPTION:{_escape(summary)}", "END:VALARM",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
