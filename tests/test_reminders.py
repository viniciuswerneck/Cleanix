import unittest
from datetime import datetime, timedelta

from cleanix import history, reminders


def _entry(days_ago, now):
    ts = (now - timedelta(days=days_ago)).isoformat(timespec='seconds')
    return history.HistoryEntry(timestamp=ts, bytes=0, files=0, categories=(), errors=0)


class ReminderDueTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 1, 31, 12, 0, 0)

    def test_disabled(self):
        self.assertFalse(reminders.is_reminder_due(7, enabled=False, now=self.now, entries=[]))

    def test_zero_interval(self):
        self.assertFalse(reminders.is_reminder_due(0, enabled=True, now=self.now, entries=[]))

    def test_no_history_is_due(self):
        self.assertTrue(reminders.is_reminder_due(7, enabled=True, now=self.now, entries=[]))

    def test_recent_not_due(self):
        entries = [_entry(3, self.now)]
        self.assertFalse(reminders.is_reminder_due(7, enabled=True, now=self.now, entries=entries))

    def test_old_is_due(self):
        entries = [_entry(10, self.now)]
        self.assertTrue(reminders.is_reminder_due(7, enabled=True, now=self.now, entries=entries))

    def test_uses_last_entry(self):
        entries = [_entry(20, self.now), _entry(2, self.now)]
        self.assertFalse(reminders.is_reminder_due(7, enabled=True, now=self.now, entries=entries))


if __name__ == '__main__':
    unittest.main()
