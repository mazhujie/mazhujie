import unittest
from datetime import date, timedelta
from render_contributions import parse_calendar, render, weeks_from_days


def fixture():
    start = date(2025, 11, 8)
    parts = ['<h2>1,201 contributions in the last year</h2>']
    for i in range(365):
        d = start+timedelta(days=i)
        count = 1200 if i == 0 else 1 if i == 364 else 0
        level = 4 if i == 0 else 1 if i == 364 else 0
        tip = f'{count:,} contributions on January 1st.' if count else 'No contributions on January 1st.'
        parts.extend([f'<td data-date="{d}" data-level="{level}" id="day-{i}"></td>',
                      f'<tool-tip for="day-{i}">{tip}</tool-tip>'])
    return ''.join(parts)


class CalendarTests(unittest.TestCase):
    def test_counts_and_date_alignment(self):
        data = parse_calendar(fixture(), 'mazhujie')
        self.assertEqual(data['total'], 1201)
        self.assertEqual(data['days'][0]['count'], 1200)
        self.assertEqual(data['days'][-1]['date'], '2026-11-07')
        weeks = weeks_from_days(data['days'])
        self.assertEqual(len(weeks[0]), 1)  # First date is Saturday, not Sunday.
        self.assertEqual(len(weeks[1]), 7)
        for mobile in (False, True):
            svg = render(data, mobile)
            self.assertEqual(svg.count('<title>202'), 365)
            self.assertIn('2025-11-08: 1200 contributions', svg)

    def test_missing_tooltip_fails_closed(self):
        bad = fixture().replace('<tool-tip for="day-0">1,200 contributions on January 1st.</tool-tip>', '')
        with self.assertRaises(ValueError):
            parse_calendar(bad, 'mazhujie')

    def test_wrong_total_fails_closed(self):
        with self.assertRaises(ValueError):
            parse_calendar(fixture().replace('1,201 contributions in the last year', '999 contributions in the last year'), 'mazhujie')

    def test_missing_date_fails_closed(self):
        bad = fixture().replace('data-date="2025-11-09"', 'data-date="2025-11-10"')
        with self.assertRaises(ValueError):
            parse_calendar(bad, 'mazhujie')


if __name__ == '__main__':
    unittest.main()
