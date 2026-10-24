"""What the model is told about the database: tables, columns, which columns are personal data, and the metric
definitions the hotel group agreed on. The SQL guard (sqlguard.py) uses the same lists, so they can't drift apart."""

TODAY = "2026-10-31"  # the synthetic data ends here; "last month" means October 2026

TABLES = {
    "properties": "id TEXT ('beach-resort' | 'mountain-lodge'), name, location, rooms_count INTEGER",
    "rooms": "id, property_id, number, room_type (Beach Resort: Ocean King, Garden Queen, Suite; Mountain Lodge: Cabin, "
    "Lodge Queen, Lodge King)",
    "guests": "id, full_name [PII], email [PII], phone [PII], loyalty_tier ('None', 'Silver', 'Gold', 'Platinum'), "
    "country (2-letter code)",
    "rates": "property_id, room_type, date (YYYY-MM-DD), rate_usd: the nightly rate loaded for that room type and date",
    "bookings": "id, property_id, room_id, guest_id, check_in, check_out (YYYY-MM-DD; check_out is the morning the guest "
    "leaves), nights, status ('confirmed' | 'completed' | 'cancelled'), channel ('direct' | 'ota' | 'phone' | "
    "'travel_agent'), booked_at, cancelled_at (NULL unless cancelled), total_usd",
    "activities": "id, property_id, name, category, price_usd, capacity",
    "activity_bookings": "id, activity_id, booking_id, date, party_size, status ('attended' | 'no_show' | 'cancelled')",
    "refunds": "id, booking_id, date, amount_usd, reason ('noise' | 'room not ready' | 'maintenance' | "
    "'billing error' | 'service')",
    "feedback": "id, booking_id, date, score (1-5), comment",
}
PII_COLUMNS = {"full_name", "email", "phone"}  # all in `guests`; only the manager role may select them

DEFINITIONS = f"""Definitions (use exactly these):
- Today is {TODAY}. "Last month" = October 2026. "This year" = 2026. Q1 = January-March.
- Revenue = SUM(bookings.total_usd) over bookings with status != 'cancelled', by check_in date.
- "Bookings" means every booking, cancelled ones included, unless the question says otherwise.
- Check-ins = bookings with status != 'cancelled', counted by check_in date.
- Room-nights sold = SUM(bookings.nights) over bookings with status != 'cancelled', by check_in date.
- ADR (average daily rate) = revenue / room-nights sold.
- Occupancy on a date = non-cancelled bookings with check_in <= date AND check_out > date, divided by
  properties.rooms_count.
- Cancellation rate = cancelled bookings / all bookings, by check_in date.
- No-show rate = no_show / (attended + no_show) in activity_bookings.
- Dates are TEXT 'YYYY-MM-DD'; use strftime / BETWEEN on them (SQLite)."""


def schema_text() -> str:
    lines = ["SQLite database of a simulated hotel group (synthetic data). Tables:"]
    lines += [f"- {name}({cols})" for name, cols in TABLES.items()]
    return "\n".join(lines) + "\n\n" + DEFINITIONS
